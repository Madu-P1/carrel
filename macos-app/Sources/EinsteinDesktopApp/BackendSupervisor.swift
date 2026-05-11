import AppKit
import Foundation
import OSLog

// File-private logger (not a class static) so it's accessible from
// background tasks. A class @MainActor + static Logger forces every
// log call to hop to the main actor, which is wrong for noisy
// background-probe paths.
private let supervisorLog = Logger(
    subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
    category: "backend-supervisor"
)

/// Watches the FastAPI backend at 127.0.0.1:8000 and spawns it when
/// missing.
///
/// Why this exists: the backend (`uvicorn main:app`) is normally started
/// by `script/build_and_run.sh::ensure_backend` before the .app boots.
/// If that step is skipped (user double-clicks the .app from Finder
/// without the script), or if the backend dies later (manual `pkill`,
/// macOS power management, OS crash recovery), the frontend has no
/// way to recover. Every `/api/*` fetch silently fails with
/// `ECONNREFUSED` and the user sees scattered "Load failed" messages
/// across the UI without any indication that the backend itself is
/// gone.
///
/// The supervisor closes that gap. On app launch it probes
/// `/api/health`; if unreachable it spawns its own uvicorn child
/// process. A timer polls every 60s and respawns on failure. On
/// app quit (`NSApplicationWillTerminate`) the supervisor terminates
/// the child so a closed .app doesn't leave an orphan listening on
/// port 8000.
///
/// Race vs. `build_and_run.sh::ensure_backend`: both can race to
/// spawn at startup. If the script wins, the supervisor's first probe
/// sees the script's uvicorn as healthy and does nothing. If the
/// supervisor wins, the script's later run will pkill the
/// supervisor's child (the script always kills stale uvicorn first,
/// per commit d3dba088) and start its own, then the supervisor's next
/// probe sees healthy. Both orderings converge on "exactly one uvicorn".
@MainActor
final class BackendSupervisor {
    /// 127.0.0.1:8000/api/health — same address the bash launcher uses.
    private let healthURL = URL(string: "http://127.0.0.1:8000/api/health")!

    /// Probe cadence after the initial start. 60s is a balance between
    /// catching crashes fast and not hammering the backend with health
    /// checks. The /api/health endpoint is cheap (no DB) so the cost
    /// per probe is negligible.
    private let probeInterval: TimeInterval = 60

    /// Per-probe timeout. The /api/health endpoint normally returns in
    /// <50ms locally; 3s is generous and covers cold starts when the
    /// supervisor itself just spawned uvicorn (Python boot + import
    /// chain is ~1.5s on this machine).
    private let probeTimeout: TimeInterval = 3

    /// Currently-running child process, if we spawned one. Nil when
    /// the script's uvicorn is the live one.
    private var process: Process?
    private var monitorTimer: Timer?

    /// Suppresses the immediate respawn after a deliberate spawn —
    /// the next probe shouldn't see the brief startup window as
    /// "unhealthy" and try to spawn a second uvicorn.
    private var lastSpawnAt: Date?
    private let spawnGraceSeconds: TimeInterval = 8

    func start() {
        supervisorLog.info("Starting backend supervisor")
        ensureRunning(reason: "launch")
        scheduleMonitor()
        installShutdownHandler()
    }

    func stop() {
        supervisorLog.info("Stopping backend supervisor")
        monitorTimer?.invalidate()
        monitorTimer = nil
        terminateChild(reason: "supervisor stop")
    }

    // MARK: - Monitor loop

    private func scheduleMonitor() {
        monitorTimer?.invalidate()
        monitorTimer = Timer.scheduledTimer(
            withTimeInterval: probeInterval,
            repeats: true
        ) { [weak self] _ in
            // Hop back to the main actor before touching state.
            Task { @MainActor [weak self] in
                self?.ensureRunning(reason: "timer")
            }
        }
    }

    private func ensureRunning(reason: String) {
        // Don't re-probe immediately after we just spawned — the
        // child needs ~1-2s to bind the port; otherwise we'd see
        // ECONNREFUSED on the next tick and double-spawn.
        if let lastSpawnAt, Date().timeIntervalSince(lastSpawnAt) < spawnGraceSeconds {
            return
        }
        Task.detached(priority: .background) { [weak self] in
            guard let self else { return }
            let healthy = await Self.probeHealth(self.healthURL, timeout: self.probeTimeout)
            if healthy {
                supervisorLog.debug("Backend healthy (\(reason, privacy: .public))")
                return
            }
            supervisorLog.notice("Backend unhealthy (\(reason, privacy: .public)) — spawning")
            await MainActor.run { self.spawn() }
        }
    }

    private static func probeHealth(_ url: URL, timeout: TimeInterval) async -> Bool {
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }
            return (200..<300).contains(http.statusCode)
        } catch {
            // ECONNREFUSED, timeout, etc. — all "not healthy".
            return false
        }
    }

    // MARK: - Spawn / teardown

    private func spawn() {
        if let existing = process, existing.isRunning {
            supervisorLog.notice("Spawn requested but child already running (pid=\(existing.processIdentifier))")
            return
        }

        let env = ProcessSpawnEnv.resolve()
        guard let env else {
            supervisorLog.error("Cannot resolve spawn env (Python or repo root missing). Backend stays down.")
            return
        }

        // Resolve the shared local-API token BEFORE the Process is
        // constructed so we can hand it to uvicorn via env. Both ends
        // (this Swift app's WebView injection and Python's
        // local_api_security middleware) must agree on the same value;
        // see LocalApiToken.swift for the audit context. If resolution
        // fails we log and continue — Python will fall back to its own
        // `secrets.token_urlsafe(32)` and the WebView's API client will
        // simply 401 on mutating calls until the user restarts. That's
        // degraded behavior, not a crash.
        let localApiToken: String?
        do {
            localApiToken = try LocalApiToken.resolve()
        } catch {
            supervisorLog.error(
                "Failed to resolve local API token: \(error.localizedDescription, privacy: .public)"
            )
            localApiToken = nil
        }

        let proc = Process()
        proc.executableURL = env.python
        proc.arguments = [
            "-m", "uvicorn",
            "main:app",
            "--host", "127.0.0.1",
            "--port", "8000",
            "--app-dir", env.repoRoot.path,
        ]
        proc.currentDirectoryURL = env.repoRoot

        // Inherit the parent environment (PATH, HOME, etc.) and then
        // overlay our token. Replacing `proc.environment` wholesale
        // with just our keys would strip everything uvicorn relies on.
        var environment = ProcessInfo.processInfo.environment
        if let localApiToken {
            environment["CARREL_LOCAL_API_TOKEN"] = localApiToken
        }
        proc.environment = environment

        // Append all output to the same log file the bash launcher
        // writes to so a single tail covers either origin.
        if let logHandle = Self.openAppendHandle(env.logURL) {
            proc.standardOutput = logHandle
            proc.standardError = logHandle
        } else {
            proc.standardOutput = FileHandle.nullDevice
            proc.standardError = FileHandle.nullDevice
        }

        do {
            try proc.run()
            process = proc
            lastSpawnAt = Date()
            supervisorLog.info("Spawned uvicorn child pid=\(proc.processIdentifier)")
        } catch {
            supervisorLog.error("Failed to spawn uvicorn: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func terminateChild(reason: String) {
        guard let proc = process, proc.isRunning else { return }
        supervisorLog.info("Terminating uvicorn child pid=\(proc.processIdentifier) (\(reason, privacy: .public))")
        proc.terminate()
        // Give it 2s to clean-shutdown; force-kill if it hangs.
        DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + 2) {
            if proc.isRunning {
                kill(proc.processIdentifier, SIGKILL)
            }
        }
        process = nil
    }

    private func installShutdownHandler() {
        NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            // willTerminate fires on quit / Cmd-Q. The block runs on the
            // main thread before the process exits, which is enough time
            // to deliver SIGTERM. Force-kill fallback runs on a
            // background queue, so it can complete during the OS's
            // ~5s teardown window.
            Task { @MainActor [weak self] in
                self?.terminateChild(reason: "app terminating")
            }
        }
    }

    private static func openAppendHandle(_ url: URL) -> FileHandle? {
        let fm = FileManager.default
        let dir = url.deletingLastPathComponent()
        if !fm.fileExists(atPath: dir.path) {
            try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        }
        if !fm.fileExists(atPath: url.path) {
            fm.createFile(atPath: url.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: url) else { return nil }
        // Discard the offset returned by seekToEnd — we use the handle
        // for write, not for measuring. `try?` discarding a throwing
        // call is what we want here; we deliberately ignore failures
        // to seek (handle still works at offset 0 if seek fails).
        _ = try? handle.seekToEnd()
        return handle
    }
}

/// Resolves the paths needed to spawn uvicorn, lazily and with
/// fallbacks. Returns nil only when the .app is launched from a
/// location that has no parent repo (e.g., copied to /Applications
/// without the source tree). In that case the user has bigger
/// problems and the supervisor should stay quiet.
private struct ProcessSpawnEnv {
    let python: URL
    let repoRoot: URL
    let logURL: URL

    static func resolve() -> ProcessSpawnEnv? {
        // The .app lives at <repo>/dist/EinsteinDesktop.app — the
        // bundle's parent's parent is the repo root.
        let bundleURL = Bundle.main.bundleURL
        let candidateRoot = bundleURL
            .deletingLastPathComponent() // dist/
            .deletingLastPathComponent() // <repo>

        // EINSTEIN_BASE_DIR override matches the bash launcher's
        // env-var contract so a user who set the path explicitly via
        // `bash script/build_and_run.sh` ends up pointing at the same
        // tree.
        let envOverride = ProcessInfo.processInfo.environment["EINSTEIN_BASE_DIR"]
            .flatMap { URL(fileURLWithPath: $0) }

        let repoRoot = envOverride ?? candidateRoot

        // Walk the candidate Python list in the same order as the bash
        // launcher: prefer the venv, fall back to system. If none
        // exist, abort.
        let pythonCandidates: [URL] = [
            repoRoot.appendingPathComponent(".venv/bin/python3"),
            repoRoot.appendingPathComponent(".venv/bin/python"),
            URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
            URL(fileURLWithPath: "/usr/bin/python3"),
        ]
        guard let python = pythonCandidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) else {
            return nil
        }

        // Sanity: main.py must be in the repo root, or uvicorn won't
        // find the app. If it's missing, we're not pointed at a real
        // Carrel checkout.
        let mainPy = repoRoot.appendingPathComponent("main.py")
        guard FileManager.default.fileExists(atPath: mainPy.path) else {
            return nil
        }

        let logURL = repoRoot.appendingPathComponent("dist/einstein-backend.log")
        return ProcessSpawnEnv(python: python, repoRoot: repoRoot, logURL: logURL)
    }
}
