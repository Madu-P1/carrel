import Foundation
import OSLog

// File-private logger so calls from background tasks don't have to
// hop to the main actor. Same pattern as BackendSupervisor and
// LocalCalendarBridge.
private let localApiTokenLog = Logger(
    subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
    category: "local-api-token"
)

/// Resolves a stable, on-disk local-API token used to authenticate
/// the SwiftUI WebView (and any future native callers) against the
/// FastAPI backend's `/api/*` endpoints.
///
/// Why this exists (audit PR-S1): the Python backend protects mutating
/// `/api/*` requests with an `X-Carrel-Local-Token` header. Before this
/// change the frontend learned the token by fetching `GET /api/local-token`
/// — an UNAUTHENTICATED endpoint. Any malicious local HTML file (or a
/// browser tab opened against `http://127.0.0.1:8000` while the app is
/// running) could `fetch('/api/local-token')` and then issue destructive
/// requests like `DELETE /api/library`. That is a local privilege
/// escalation against a single-user trust boundary.
///
/// The fix flips the source of truth: Swift owns the token, persists it
/// on disk, and hands it to BOTH ends — Python via the
/// `CARREL_LOCAL_API_TOKEN` env var on spawn, and the WebView via a
/// `WKUserScript` injected at document-start. The Python `GET
/// /api/local-token` route goes away in a sibling PR; the frontend
/// stops fetching it and reads `window.__CARREL_LOCAL_API_TOKEN`
/// instead.
///
/// Format: 32 random bytes encoded as URL-safe base64 (no padding).
/// Matches Python's `secrets.token_urlsafe(32)` shape so swapping the
/// two ends is transparent and a token from either origin parses on
/// the other.
///
/// Storage: `~/Library/Application Support/Carrel/local-api-token`,
/// mode `0600` (owner read+write only). Defense in depth against
/// other-user inspection on shared Macs; the file's contents are
/// cleartext but the mode keeps casual snoops out. The mode is
/// re-asserted on every `resolve()` call so a manual `chmod 644`
/// drift gets healed silently.
enum LocalApiToken {
    /// Returns the persisted token, creating one on first call.
    /// Throws `LocalApiTokenError` on filesystem failures so the
    /// caller can decide whether to degrade gracefully or surface
    /// the error.
    static func resolve() throws -> String {
        let url = try tokenFileURL()
        return try resolveOrCreateToken(at: url)
    }

    /// Internal seam: read the token at `url` if the file exists,
    /// otherwise generate, persist with mode 0600, and return it.
    /// `resolve()` calls this with the default Application Support
    /// path; tests call it with a temp-directory URL so the suite
    /// stays out of the user's real Application Support tree.
    static func resolveOrCreateToken(at url: URL) throws -> String {
        let fm = FileManager.default

        if fm.fileExists(atPath: url.path) {
            // Existing token — read, sanity-check, re-assert mode.
            guard let data = try? Data(contentsOf: url) else {
                throw LocalApiTokenError.readFailed(url: url)
            }
            guard let token = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines),
                !token.isEmpty
            else {
                throw LocalApiTokenError.malformed(url: url)
            }
            applyOwnerOnlyMode(to: url)
            return token
        }

        // First call — generate and persist.
        let token = generateToken()
        guard let data = token.data(using: .utf8) else {
            throw LocalApiTokenError.encodingFailed
        }
        do {
            try data.write(to: url, options: [.atomic])
        } catch {
            throw LocalApiTokenError.writeFailed(url: url, underlying: error)
        }
        applyOwnerOnlyMode(to: url)
        localApiTokenLog.info("Generated new local API token at \(url.path, privacy: .public)")
        return token
    }

    // MARK: - Internals

    /// `~/Library/Application Support/Carrel/local-api-token`, with
    /// the parent directory created if missing.
    private static func tokenFileURL() throws -> URL {
        let fm = FileManager.default
        let appSupport: URL
        do {
            appSupport = try fm.url(
                for: .applicationSupportDirectory,
                in: .userDomainMask,
                appropriateFor: nil,
                create: true
            )
        } catch {
            throw LocalApiTokenError.appSupportUnavailable(underlying: error)
        }
        return try tokenFileURL(baseDirectory: appSupport)
    }

    /// Internal seam: build the `Carrel/local-api-token` URL inside an
    /// arbitrary base directory, creating the `Carrel/` subdirectory
    /// on demand. `tokenFileURL()` passes the user's Application
    /// Support directory; tests pass a temp directory so the suite
    /// never touches the real Carrel data path.
    static func tokenFileURL(baseDirectory: URL) throws -> URL {
        let fm = FileManager.default
        let carrelDir = baseDirectory.appendingPathComponent("Carrel", isDirectory: true)
        if !fm.fileExists(atPath: carrelDir.path) {
            do {
                try fm.createDirectory(at: carrelDir, withIntermediateDirectories: true)
            } catch {
                throw LocalApiTokenError.directoryCreateFailed(url: carrelDir, underlying: error)
            }
        }
        return carrelDir.appendingPathComponent("local-api-token", isDirectory: false)
    }

    /// 32 random bytes → URL-safe base64 with padding stripped.
    /// Matches `secrets.token_urlsafe(32)` from the Python side
    /// character-for-character.
    private static func generateToken() -> String {
        let bytes = (0..<32).map { _ in UInt8.random(in: 0...255) }
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "=", with: "")
    }

    /// Re-assert `0600` on every resolve so a manual chmod that loosens
    /// the file gets corrected. Best-effort: log on failure but don't
    /// throw — the token is still usable even if the mode drifts.
    private static func applyOwnerOnlyMode(to url: URL) {
        do {
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o600],
                ofItemAtPath: url.path
            )
        } catch {
            localApiTokenLog.error(
                "Failed to set 0600 mode on \(url.path, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
        }
    }
}

enum LocalApiTokenError: LocalizedError {
    case appSupportUnavailable(underlying: Error)
    case directoryCreateFailed(url: URL, underlying: Error)
    case writeFailed(url: URL, underlying: Error)
    case readFailed(url: URL)
    case malformed(url: URL)
    case encodingFailed

    var errorDescription: String? {
        switch self {
        case let .appSupportUnavailable(error):
            return "Unable to locate Application Support directory: \(error.localizedDescription)"
        case let .directoryCreateFailed(url, error):
            return "Failed to create token directory at \(url.path): \(error.localizedDescription)"
        case let .writeFailed(url, error):
            return "Failed to write local API token to \(url.path): \(error.localizedDescription)"
        case let .readFailed(url):
            return "Failed to read local API token from \(url.path)"
        case let .malformed(url):
            return "Local API token at \(url.path) is empty or malformed"
        case .encodingFailed:
            return "Failed to encode local API token as UTF-8"
        }
    }
}
