import AppKit
import OSLog
import WebKit

private let companionLog = Logger(
    subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
    category: "floating-companion"
)

/// A borderless, always-on-top NSPanel hosting a tiny WKWebView that
/// renders the cube companion (`Resources/companion-floating.html`).
///
/// Why an NSPanel and not an NSWindow:
///   - .nonactivatingPanel collection style means clicking the
///     companion does not steal focus from whatever the user is working
///     in. The user can drag it without their text cursor leaving Notion
///     (or whatever's frontmost).
///   - .floating window level keeps it above normal app windows. Set
///     once at construction; AppKit handles the rest.
///   - .canJoinAllSpaces collection behavior makes it follow the user
///     across desktop spaces, including fullscreen apps. Same trick
///     window-managers use for their menu bars.
///
/// Why WKWebView and not native SwiftUI:
///   - The cube already exists as polished HTML/CSS/JS. Re-implementing
///     the 3D faces, the per-state behaviors, the ambient pulser, and
///     the animation cadence in SwiftUI would burn days. The companion
///     bundle is ~30 KB; a single WKWebView is the right fit.
///   - The Carrel app already pays the WKWebView startup cost for its
///     main window. A second instance is cheap.
///
/// Lifecycle:
///   - `start()` constructs the panel, loads the bundled HTML, and
///     orders front. Idempotent.
///   - `setState(_:)` evaluates `window.companion.setState('name')`
///     inside the WKWebView. Quietly no-ops if the state name is not
///     one of the nine known states.
///   - `stop()` orders the panel out and lets ARC release the WKWebView.
@MainActor
final class FloatingCompanionWindow: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
    /// Singleton — there is only ever one floating companion. The Swift
    /// API is intentionally narrow: bridge handlers and AppDelegate
    /// hold a strong reference; nothing else should construct one.
    static let shared = FloatingCompanionWindow()

    /// Panel is sized to comfortably fit the 200×200 cube plus margin
    /// for scale/rotation overhang and the aura glow. The cube is the
    /// only visible — there is no shell, label, or pill.
    private let panelSize = NSSize(width: 160, height: 160)
    private let edgeInset: CGFloat = 24

    /// JS-side handler name for the drag/tap bridge. Kept distinct from
    /// the in-app `nativeCompanion` handler so the two surfaces can
    /// evolve independently.
    private let shellHandlerName = "companionShell"

    private var panel: NSPanel?
    private var webView: DropAcceptingWebView?
    private var didFinishInitialLoad = false

    /// URLSession used for token fetch + multipart upload. Ephemeral so
    /// the cookie store is not persisted (we use a header token, not
    /// cookies).
    private let session = URLSession(configuration: .ephemeral)
    private let backendBase = URL(string: "http://127.0.0.1:8000")!
    private let localTokenHeader = "X-Carrel-Local-Token"
    private var cachedLocalToken: String?

    /// Bridge calls that arrive before the WKWebView finishes loading
    /// are queued as closures and replayed in order on
    /// `webView(_:didFinish:)`. Closures keep the queue trivially
    /// extensible — adding setX(...) doesn't need a new "pending"
    /// field or string-encoding scheme.
    private var pendingCalls: [() -> Void] = []

    /// True while the cube is in alarm-spin mode (scheduled study session
    /// is due). Tap during alarm acks-and-dismisses instead of opening
    /// the main window.
    private var alarmActive = false

    func start() {
        if panel != nil { return }
        guard let url = Bundle.main.url(forResource: "companion-floating", withExtension: "html") else {
            companionLog.error("companion-floating.html not found in bundle; floating companion stays down.")
            return
        }
        let panel = makePanel()
        let webView = makeWebView()
        panel.contentView = webView
        webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        positionAtBottomRight(panel)
        // .nonactivating order means the panel comes to the front but
        // the previously-frontmost app stays key. The user can drag the
        // companion out of their study app's way without losing typing
        // focus.
        panel.orderFrontRegardless()
        self.panel = panel
        self.webView = webView
        companionLog.info("Floating companion window opened.")
    }

    func stop() {
        // Tear down the script handler before dropping the WebView so
        // the WKUserContentController doesn't keep a strong reference
        // to self. Mirrors the dismantleNSView pattern in WebAppView.
        webView?.configuration.userContentController.removeScriptMessageHandler(forName: shellHandlerName)
        panel?.orderOut(nil)
        panel = nil
        webView = nil
        didFinishInitialLoad = false
        pendingCalls.removeAll()
    }

    /// If the WebView has finished its initial load, run `now()`
    /// immediately; otherwise queue it for replay on didFinish.
    private func whenLoaded(_ now: @escaping () -> Void) {
        if didFinishInitialLoad { now() }
        else { pendingCalls.append(now) }
    }

    /// Push a state into the cube. Allowed names match the JS side's
    /// STATES table: idle | focused | thinking | citeChecking |
    /// encouraging | stumped | break | sleeping | streak.
    /// Unknown names are silently dropped (the WKWebView's setState
    /// no-ops on unknowns too — defense in depth).
    func setState(_ name: String) {
        guard Self.allowedStates.contains(name) else {
            companionLog.warning("Ignoring unknown companion state \(name, privacy: .public)")
            return
        }
        whenLoaded { [weak self] in
            self?.evaluate("window.companion?.setState(\(self?.jsString(name) ?? "\"\""))")
        }
    }

    /// Toggle alarm-spin mode. Sticky — stays on until cleared.
    func setAlarm(_ active: Bool) {
        alarmActive = active
        whenLoaded { [weak self] in
            self?.evaluate("window.companion?.setAlarm(\(active ? "true" : "false"))")
        }
    }

    /// Update the streak day count surfaced in the pill.
    func setStreakDays(_ days: Int) {
        let clamped = max(0, days)
        whenLoaded { [weak self] in
            self?.evaluate("window.companion?.setStreakDays(\(clamped))")
        }
    }

    // MARK: - WKNavigationDelegate

    nonisolated func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        Task { @MainActor [weak self] in
            self?.didFinishInitialLoad = true
            self?.replayPending()
        }
    }

    // MARK: - Internals

    /// Allowed state names. Mirrors the JS STATES keys; kept in Swift so
    /// the type system can guard the bridge boundary. If you add a new
    /// state to the JS, add it here too.
    static let allowedStates: Set<String> = [
        "idle", "focused", "thinking", "citeChecking",
        "encouraging", "stumped", "break", "sleeping", "streak",
    ]

    private func replayPending() {
        let calls = pendingCalls
        pendingCalls.removeAll()
        for call in calls { call() }
    }

    private func makePanel() -> NSPanel {
        let style: NSWindow.StyleMask = [.borderless, .nonactivatingPanel]
        let panel = NSPanel(
            contentRect: NSRect(origin: .zero, size: panelSize),
            styleMask: style,
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        panel.hidesOnDeactivate = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.isMovableByWindowBackground = true
        panel.isReleasedWhenClosed = false
        // Don't show in the window menu / mission control.
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        return panel
    }

    private func makeWebView() -> DropAcceptingWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        let controller = WKUserContentController()
        controller.add(self, name: shellHandlerName)
        config.userContentController = controller
        let webView = DropAcceptingWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        webView.allowsBackForwardNavigationGestures = false
        webView.onFilesEnter = { [weak self] in self?.handleFilesEnter() }
        webView.onFilesExit = { [weak self] in self?.handleFilesExit() }
        webView.onFilesDropped = { [weak self] urls in self?.handleFilesDropped(urls) }
        return webView
    }

    // MARK: - File drop bridge

    private func handleFilesEnter() {
        evaluate("window.companion?.setDropping(true)")
    }

    private func handleFilesExit() {
        evaluate("window.companion?.setDropping(false)")
    }

    private func handleFilesDropped(_ urls: [URL]) {
        evaluate("window.companion?.setDropping(false)")
        guard !urls.isEmpty else { return }
        evaluate("window.companion?.setState(\(jsString("thinking")))")
        Task { [weak self] in
            await self?.uploadDroppedFiles(urls)
        }
    }

    private func uploadDroppedFiles(_ urls: [URL]) async {
        var successes = 0
        var failures = 0
        for url in urls {
            let ok = await uploadOne(url)
            if ok { successes += 1 } else { failures += 1 }
        }
        let resultState = failures == 0 ? "encouraging" : "stumped"
        evaluate("window.companion?.setState(\(jsString(resultState)))")
        // Nudge the main Carrel webview to refresh its library list.
        // The library SSE stream usually catches this on its own, but
        // we belt-and-suspenders nudge here in case the stream is
        // offline. Retry briefly because the main webview may still be
        // booting on first launch (the cube can fire before the React
        // app has registered the global hook).
        if successes > 0 {
            Task { [weak self] in await self?.nudgeLibraryRefresh() }
        }
        // Snap back to idle so the cube doesn't get stuck on a celebratory
        // face after the user moves on. Same cadence the in-app states use.
        try? await Task.sleep(nanoseconds: 2_400_000_000)
        evaluate("window.companion?.setState(\(jsString("idle")))")
        companionLog.info(
            "Companion file drop: \(successes, privacy: .public) ok, \(failures, privacy: .public) failed."
        )
    }

    private func nudgeLibraryRefresh() async {
        // Up to 4 attempts, ~3s total. The hook is set up on the very
        // first JS line of main.tsx, so this normally lands on attempt
        // 1; the retries cover cold launches.
        for _ in 0..<4 {
            let landed: Bool = await withCheckedContinuation { continuation in
                guard let webView = WebViewRegistry.current else {
                    continuation.resume(returning: false)
                    return
                }
                webView.evaluateJavaScript(
                    "typeof window.__carrelRefreshLibrary === 'function' ? (window.__carrelRefreshLibrary(), true) : false"
                ) { result, _ in
                    continuation.resume(returning: (result as? Bool) == true)
                }
            }
            if landed { return }
            try? await Task.sleep(nanoseconds: 750_000_000)
        }
        companionLog.warning("Library refresh nudge could not reach the main webview after 4 attempts.")
    }

    private func uploadOne(_ url: URL) async -> Bool {
        // Two attempts: the first may race a stale cached token (backend
        // restarted between drops), so on 403 we bust the cache and retry
        // once. Anything past attempt 2 isn't transient — surface it.
        for attempt in 1...2 {
            guard let token = await fetchLocalToken() else {
                companionLog.error(
                    "Cannot upload \(url.lastPathComponent, privacy: .public) (attempt \(attempt, privacy: .public)): no local token."
                )
                // Backend may still be booting. Wait briefly before retry.
                try? await Task.sleep(nanoseconds: 500_000_000)
                continue
            }
            let endpoint = backendBase.appendingPathComponent("api/jobs/import")
            let boundary = "Boundary-\(UUID().uuidString)"
            var request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            request.setValue(token, forHTTPHeaderField: localTokenHeader)
            request.timeoutInterval = 60
            let body: Data
            do {
                body = try makeMultipartBody(boundary: boundary, fileURL: url, subjectName: "General")
            } catch {
                companionLog.error(
                    "Failed to read \(url.lastPathComponent, privacy: .public): \(error.localizedDescription, privacy: .public)"
                )
                return false
            }
            request.httpBody = body
            do {
                let (_, response) = try await session.data(for: request)
                guard let http = response as? HTTPURLResponse else { return false }
                if http.statusCode == 403 {
                    // Token went stale (backend restarted). Bust + retry.
                    cachedLocalToken = nil
                    companionLog.warning(
                        "Upload \(url.lastPathComponent, privacy: .public) got 403; refreshing token and retrying."
                    )
                    continue
                }
                let ok = (200..<300).contains(http.statusCode) || http.statusCode == 409
                if !ok {
                    companionLog.error(
                        "Upload \(url.lastPathComponent, privacy: .public) failed status=\(http.statusCode, privacy: .public)"
                    )
                }
                return ok
            } catch {
                companionLog.error(
                    "Upload failed for \(url.lastPathComponent, privacy: .public) (attempt \(attempt, privacy: .public)): \(error.localizedDescription, privacy: .public)"
                )
                if attempt == 2 { return false }
                try? await Task.sleep(nanoseconds: 750_000_000)
            }
        }
        return false
    }

    private func makeMultipartBody(boundary: String, fileURL: URL, subjectName: String) throws -> Data {
        var body = Data()
        let crlf = "\r\n"
        let appendString: (String) -> Void = { body.append($0.data(using: .utf8) ?? Data()) }
        // file part — match the field name `file` used by /api/jobs/import.
        appendString("--\(boundary)\(crlf)")
        let filename = fileURL.lastPathComponent
        let mime = mimeType(for: fileURL)
        appendString("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\(crlf)")
        appendString("Content-Type: \(mime)\(crlf)\(crlf)")
        body.append(try Data(contentsOf: fileURL))
        appendString(crlf)
        // subject_name part — same default the library dropzone uses.
        appendString("--\(boundary)\(crlf)")
        appendString("Content-Disposition: form-data; name=\"subject_name\"\(crlf)\(crlf)")
        appendString("\(subjectName)\(crlf)")
        appendString("--\(boundary)--\(crlf)")
        return body
    }

    private func mimeType(for url: URL) -> String {
        UploadMimeTypes.mimeType(for: url)
    }

    /// Same shape as LocalCalendarBridge.fetchLocalToken — Carrel's
    /// `/api/local-token` endpoint is unauthenticated so the frontend
    /// can bootstrap. Cache for the lifetime of the panel; bust on 403.
    private func fetchLocalToken() async -> String? {
        if let cachedLocalToken { return cachedLocalToken }
        let url = backendBase.appendingPathComponent("api/local-token")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                return nil
            }
            let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            if let token = payload?["token"] as? String, !token.isEmpty {
                cachedLocalToken = token
                return token
            }
            return nil
        } catch {
            return nil
        }
    }

    // MARK: - WKScriptMessageHandler

    /// JS posts {action, ...} to "companionShell". WKWebView captures
    /// the OS-level mouse events before the NSPanel can see them, so
    /// the panel's built-in `isMovableByWindowBackground` does nothing.
    /// We do the panel move here instead, in response to JS deltas.
    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        handleShellMessage(message.body)
    }

    private func handleShellMessage(_ body: Any) {
        guard let dict = body as? [String: Any],
              let action = dict["action"] as? String else { return }
        switch action {
        case "dragStart":
            // No-op for now; reserved for a hover-state hook if we
            // later want to dim other UI while the user is repositioning.
            break
        case "dragMove":
            let dx = (dict["dx"] as? NSNumber)?.doubleValue ?? 0
            let dy = (dict["dy"] as? NSNumber)?.doubleValue ?? 0
            applyDragDelta(dx: CGFloat(dx), dy: CGFloat(dy))
        case "dragEnd":
            break
        case "tap":
            handleTap()
        default:
            companionLog.warning("Unknown companionShell action \(action, privacy: .public)")
        }
    }

    private func applyDragDelta(dx: CGFloat, dy: CGFloat) {
        guard let panel else { return }
        // JS pointer events: screenY increases downward. AppKit window
        // origin: y increases upward. So panel y -= dy.
        let origin = panel.frame.origin
        panel.setFrameOrigin(NSPoint(x: origin.x + dx, y: origin.y - dy))
    }

    private func handleTap() {
        // Tap during alarm = "I see it, I'm coming". Dismiss the spin,
        // notify the main app's bus to clear its alarm flag, AND bring
        // Carrel forward so the user can hit Start. Without the main-app
        // notification the bus would re-fire the alarm next tick.
        if alarmActive {
            setAlarm(false)
            WebViewRegistry.current?.evaluateJavaScript(
                "window.dispatchEvent(new CustomEvent('carrel:companion-alarm-ack'))",
                completionHandler: nil
            )
        }
        NSApp.activate(ignoringOtherApps: true)
        let mainWindow = NSApp.windows.first { window in
            !(window is NSPanel) && window.canBecomeKey
        }
        guard let mainWindow else {
            companionLog.warning("Tap: no main Carrel window found.")
            return
        }
        if mainWindow.isMiniaturized { mainWindow.deminiaturize(nil) }
        mainWindow.makeKeyAndOrderFront(nil)
    }

    private func positionAtBottomRight(_ panel: NSPanel) {
        let screen = NSScreen.main ?? NSScreen.screens.first
        guard let screen else { return }
        let visible = screen.visibleFrame
        let origin = NSPoint(
            x: visible.maxX - panelSize.width - edgeInset,
            y: visible.minY + edgeInset,
        )
        panel.setFrameOrigin(origin)
    }

    private func evaluate(_ source: String) {
        guard let webView else { return }
        webView.evaluateJavaScript(source) { _, error in
            if let error {
                companionLog.error(
                    "evaluateJavaScript failed: \(error.localizedDescription, privacy: .public)"
                )
            }
        }
    }

    /// Encode a Swift String as a JS string literal. Uses JSONSerialization
    /// so embedded quotes / backslashes / unicode all survive correctly.
    private func jsString(_ value: String) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: [value], options: []),
              let jsonArray = String(data: data, encoding: .utf8) else {
            return "\"\""
        }
        // jsonArray looks like `["focused"]`; strip the brackets.
        let trimmed = jsonArray.dropFirst().dropLast()
        return String(trimmed)
    }
}

extension Notification.Name {
    /// Posted when the user taps (mousedown→mouseup with no movement)
    /// the floating companion. Listeners decide what action to take —
    /// open Carrel, cycle states, summon a quick-action menu, etc.
    static let floatingCompanionTapped = Notification.Name("floatingCompanionTapped")
}

/// WKWebView subclass that intercepts file drops at the AppKit level so
/// the cube can act as a desktop drop-target. WKWebView's HTML5 drop
/// support is unreliable for `file://`-loaded pages — Safari/WebKit will
/// often try to navigate to the dropped file's URL instead of letting JS
/// handle it. By registering for `.fileURL` here and overriding the
/// dragging-destination methods, we short-circuit that behavior and hand
/// the URLs back to FloatingCompanionWindow for upload.
@MainActor
final class DropAcceptingWebView: WKWebView {
    var onFilesEnter: (() -> Void)?
    var onFilesExit: (() -> Void)?
    var onFilesDropped: (([URL]) -> Void)?

    override init(frame: CGRect, configuration: WKWebViewConfiguration) {
        super.init(frame: frame, configuration: configuration)
        registerForDraggedTypes([.fileURL])
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        if !readFileURLs(from: sender).isEmpty {
            onFilesEnter?()
            return .copy
        }
        return super.draggingEntered(sender)
    }

    override func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation {
        if !readFileURLs(from: sender).isEmpty { return .copy }
        return super.draggingUpdated(sender)
    }

    override func draggingExited(_ sender: NSDraggingInfo?) {
        onFilesExit?()
        super.draggingExited(sender)
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let urls = readFileURLs(from: sender)
        if !urls.isEmpty {
            onFilesDropped?(urls)
            return true
        }
        return super.performDragOperation(sender)
    }

    private func readFileURLs(from info: NSDraggingInfo) -> [URL] {
        let options: [NSPasteboard.ReadingOptionKey: Any] = [.urlReadingFileURLsOnly: true]
        let items = info.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: options) as? [URL]
        return items ?? []
    }
}
