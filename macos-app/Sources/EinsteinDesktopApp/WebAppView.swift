import AppKit
import OSLog
import SwiftUI
import WebKit

struct WebAppView: NSViewRepresentable {
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: NativeBridge.storageHandlerName)
        contentController.add(context.coordinator, name: NativeBridge.externalOpenHandlerName)
        contentController.add(context.coordinator, name: NativeBridge.menuHandlerName)
        contentController.add(context.coordinator, name: NativeBridge.telemetryHandlerName)
        contentController.add(context.coordinator, name: NativeBridge.frontendHandlerName)
        contentController.addUserScript(
            WKUserScript(
                source: NativeBridge.bootstrapScript,
                injectionTime: .atDocumentStart,
                forMainFrameOnly: true
            )
        )

        let configuration = WKWebViewConfiguration()
        configuration.userContentController = contentController
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true

        // WKWebView treats every file:// URL as its own opaque origin by
        // default. Two KVC preferences are required to make the bundled app
        // load correctly:
        //
        //   allowFileAccessFromFileURLs (narrow scope — same-file-origin)
        //     Needed so ES dynamic imports like `import("./pdf.js")` inside
        //     the new bundle can reach sibling file:// chunks without being
        //     rejected as cross-origin.
        //
        //   allowUniversalAccessFromFileURLs (broader scope — file-to-any)
        //     Needed for the LEGACY bundle (`app.html.legacy`), which loads
        //     KaTeX from cdnjs and makes direct HTTPS calls to Anthropic and
        //     OpenAI for its own model pipeline. Without this, every https://
        //     fetch from a file:// page is blocked and the legacy app never
        //     boots — blank WebView.
        //
        // Security posture: both HTML bundles are first-party artifacts we
        // ship in the app. User-uploaded PDFs are parsed by pdf.js as data
        // and rendered to canvas/text layers; they are never loaded as HTML
        // documents, so they cannot exploit these file:// loosenings. The
        // new bundle's `tests/bundle-integrity.test.ts` also blocks any
        // future third-party host references, keeping the local-first
        // promise for the modern code path.
        configuration.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator

        if #available(macOS 13.3, *) {
            webView.isInspectable = true
        }

        context.coordinator.attach(to: webView)
        context.coordinator.loadBundledApp(into: webView)

        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}

    static func dismantleNSView(_ nsView: WKWebView, coordinator: Coordinator) {
        nsView.configuration.userContentController.removeScriptMessageHandler(
            forName: NativeBridge.storageHandlerName
        )
        nsView.configuration.userContentController.removeScriptMessageHandler(
            forName: NativeBridge.externalOpenHandlerName
        )
        nsView.configuration.userContentController.removeScriptMessageHandler(
            forName: NativeBridge.menuHandlerName
        )
        nsView.configuration.userContentController.removeScriptMessageHandler(
            forName: NativeBridge.telemetryHandlerName
        )
        nsView.configuration.userContentController.removeScriptMessageHandler(
            forName: NativeBridge.frontendHandlerName
        )
        WebViewRegistry.unregister(nsView)
    }
}

@MainActor
final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler, WKUIDelegate {
    private weak var webView: WKWebView?
    private var didLogInteractive = false
    /// Which frontend is currently loaded. Tracked here (not via
    /// FrontendSelector.resolved()) because resolved() honors the launch
    /// env var even after a user clicks "Switch to new frontend." The
    /// escape-hatch injection in didFinish needs to know what's actually
    /// on screen, not what the env var prefers.
    private var activeFrontend: Frontend = .new
    private let logger = Logger(
        subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
        category: "webview"
    )

    func attach(to webView: WKWebView) {
        self.webView = webView
        WebViewRegistry.register(webView)
    }

    /// Load the bundled web app.
    ///
    /// `explicitFrontend` lets a caller force a specific frontend regardless
    /// of the `EINSTEIN_FRONTEND` env var — used by the Carrel > Frontend
    /// menu so a user's click beats the launch-time env default. Normal boot
    /// (makeNSView) passes nil and goes through FrontendSelector.resolved().
    func loadBundledApp(into webView: WKWebView, explicitFrontend: Frontend? = nil) {
        didLogInteractive = false
        let activeFrontend = explicitFrontend ?? FrontendSelector.resolved()
        self.activeFrontend = activeFrontend
        let resource = FrontendSelector.bundledResource(for: activeFrontend)
        guard let htmlURL = Bundle.main.url(forResource: resource.name, withExtension: resource.ext) else {
            logger.error("Missing bundled HTML resource \(resource.name).\(resource.ext)")
            webView.loadHTMLString(
                """
                <!DOCTYPE html>
                <html>
                <body style="font-family: -apple-system; background: #111; color: #f5f5f5; padding: 32px;">
                  <h1>Carrel failed to load</h1>
                  <p>The bundled HTML resource was not found inside the app.</p>
                </body>
                </html>
                """,
                baseURL: nil
            )
            return
        }

        logger.info("Loading bundled web app from \(htmlURL.path(percentEncoded: false), privacy: .public)")

        // New bundle: loadFileURL so relative asset paths (./assets.new/index.css,
        // ./assets.new/instrument-serif-latin-400.woff2, the pdf.js chunk) resolve
        // correctly against the Resources directory under file://.
        //
        // Legacy bundle: loadHTMLString with a synthetic HTTP base URL. Why HTTP
        // and not HTTPS:
        //   - Cross-origin HTTPS fetches (cdnjs for KaTeX, api.anthropic.com,
        //     api.openai.com) succeed from an http:// origin — browsers allow
        //     scheme upgrades, just not downgrades.
        //   - The local backend at http://127.0.0.1:8000 is plain HTTP. From an
        //     https:// origin, WebKit blocks that as mixed content and the UI
        //     shows "Local study engine unavailable." An http:// origin lets
        //     the loopback call through while HTTPS outbound still works.
        // Under a file:// origin all of the above fail as cross-origin, which
        // is why we need a synthetic origin at all. See
        // docs/notes/2026-04-21-legacy-https-origin.md for the full history.
        if activeFrontend == .legacy {
            guard let html = try? String(contentsOf: htmlURL, encoding: .utf8) else {
                logger.error("Failed to read legacy HTML at \(htmlURL.path(percentEncoded: false), privacy: .public)")
                return
            }
            let baseURL = URL(string: "http://einstein.local/")
            webView.loadHTMLString(html, baseURL: baseURL)
            return
        }

        webView.loadFileURL(htmlURL, allowingReadAccessTo: htmlURL.deletingLastPathComponent())
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        switch message.name {
        case NativeBridge.storageHandlerName:
            handleStorageMessage(message.body)
        case NativeBridge.externalOpenHandlerName:
            handleExternalOpenMessage(message.body)
        case NativeBridge.menuHandlerName:
            logger.info("Received reserved nativeMenu bridge message")
        case NativeBridge.telemetryHandlerName:
            handleTelemetryMessage(message.body)
        case NativeBridge.frontendHandlerName:
            handleFrontendMessage(message.body)
        default:
            logger.warning("Unhandled script message: \(message.name, privacy: .public)")
        }
    }

    private func handleFrontendMessage(_ body: Any) {
        guard
            let payload = body as? [String: Any],
            let action = payload["action"] as? String
        else {
            logger.error("Received malformed nativeFrontend payload")
            return
        }
        guard action == "switch" else {
            logger.warning("nativeFrontend: unsupported action \(action, privacy: .public)")
            return
        }
        guard
            let rawMode = payload["mode"] as? String,
            let frontend = Frontend(rawValue: rawMode.lowercased())
        else {
            logger.error("nativeFrontend: invalid mode in payload")
            return
        }
        FrontendSelector.setUserPreference(frontend)
        logger.info("Switching frontend to \(frontend.rawValue, privacy: .public)")
        guard let webView = self.webView else { return }
        loadBundledApp(into: webView, explicitFrontend: frontend)
    }

    private func handleStorageMessage(_ body: Any) {
        guard
            let payload = body as? [String: Any],
            let requestID = payload["id"] as? Int,
            let action = payload["action"] as? String,
            let key = payload["key"] as? String
        else {
            logger.error("Received malformed storage payload")
            return
        }

        do {
            switch action {
            case "get":
                let value = UserDefaults.standard.string(forKey: storageKey(for: key))
                logger.info("Storage get for key \(key, privacy: .public)")
                resolveStorageRequest(id: requestID, payload: ["value": value ?? NSNull()])
            case "set":
                if let value = payload["value"] as? String {
                    UserDefaults.standard.set(value, forKey: storageKey(for: key))
                } else {
                    UserDefaults.standard.removeObject(forKey: storageKey(for: key))
                }
                logger.info("Storage set for key \(key, privacy: .public)")
                resolveStorageRequest(id: requestID, payload: ["ok": true])
            default:
                throw BridgeError.unsupportedAction(action)
            }
        } catch {
            logger.error("Storage bridge failed: \(error.localizedDescription, privacy: .public)")
            rejectStorageRequest(id: requestID, message: error.localizedDescription)
        }
    }

    private func handleExternalOpenMessage(_ body: Any) {
        guard
            let payload = body as? [String: Any],
            let rawURL = payload["url"] as? String,
            let url = URL(string: rawURL)
        else {
            logger.error("Received malformed external URL payload")
            return
        }

        openExternal(url)
    }

    private func handleTelemetryMessage(_ body: Any) {
        guard
            let payload = body as? [String: Any],
            let event = payload["event"] as? String
        else {
            logger.error("Received malformed telemetry payload")
            return
        }

        let details = payload["payload"] as? [String: Any] ?? [:]
        switch event {
        case "app-interactive":
            let route = (details["route"] as? String) ?? "unknown"
            let perfNowMilliseconds = details["perfNowMs"] as? Double
            logInteractiveOnce(route: route, performanceNowMilliseconds: perfNowMilliseconds)
        case "main-script-start", "main-script-rendered":
            logger.info(
                "Frontend telemetry \(event, privacy: .public): \(String(describing: details), privacy: .public)"
            )
        case "main-script-timeout", "window-error", "unhandled-rejection":
            logger.error(
                "Frontend telemetry \(event, privacy: .public): \(String(describing: details), privacy: .public)"
            )
        default:
            logger.info("Ignoring telemetry event \(event, privacy: .public)")
        }
    }

    private func logInteractiveOnce(route: String, performanceNowMilliseconds: Double?) {
        guard !didLogInteractive else {
            return
        }

        didLogInteractive = true
        LaunchTelemetry.markInteractive(
            frontend: FrontendSelector.resolved().rawValue,
            route: route,
            performanceNowMilliseconds: performanceNowMilliseconds
        )
    }

    private func probeInteractiveMarker(attempt: Int = 0) {
        guard !didLogInteractive, attempt < 200 else {
            return
        }

        webView?.evaluateJavaScript(
            "window.__einsteinInteractivePayload ? JSON.stringify(window.__einsteinInteractivePayload) : null"
        ) { [weak self] result, error in
            guard let self else {
                return
            }

            if let error {
                self.logger.debug(
                    "Interactive probe skipped: \(error.localizedDescription, privacy: .public)"
                )
            } else if
                let jsonString = result as? String,
                let data = jsonString.data(using: .utf8),
                let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let route = payload["route"] as? String
            {
                let perfNowMilliseconds = payload["perfNowMs"] as? Double
                self.logInteractiveOnce(route: route, performanceNowMilliseconds: perfNowMilliseconds)
                return
            }

            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                self.probeInteractiveMarker(attempt: attempt + 1)
            }
        }
    }

    private func storageKey(for key: String) -> String {
        let prefix = Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop"
        return "\(prefix).\(key)"
    }

    private func resolveStorageRequest(id: Int, payload: [String: Any]) {
        evaluateJavaScript("window.__nativeStorageResolve(\(id), \(jsonString(for: payload)));")
    }

    private func rejectStorageRequest(id: Int, message: String) {
        let payload = jsonString(for: ["message": message])
        evaluateJavaScript("window.__nativeStorageReject(\(id), \(payload));")
    }

    private func evaluateJavaScript(_ source: String) {
        webView?.evaluateJavaScript(source) { _, error in
            if let error {
                self.logger.error("Bridge JS evaluation failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    private func jsonString(for object: Any) -> String {
        guard
            JSONSerialization.isValidJSONObject(object),
            let data = try? JSONSerialization.data(withJSONObject: object, options: []),
            let json = String(data: data, encoding: .utf8)
        else {
            return "null"
        }

        return json
    }

    private func openExternal(_ url: URL) {
        logger.info("Opening external URL \(url.absoluteString, privacy: .public)")
        NSWorkspace.shared.open(url)
    }

    private func presentAlert(message: String, style: NSAlert.Style = .informational) -> NSAlert {
        let alert = NSAlert()
        alert.alertStyle = style
        alert.messageText = "Carrel"
        alert.informativeText = message
        return alert
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        logger.info("Finished loading bundled web app")
        probeInteractiveMarker()
        installLegacyEscapeHatchIfNeeded(webView)
    }

    /// Inject a small floating "← New frontend" pill into the legacy bundle.
    ///
    /// The legacy HTML is a 310 KB blob we don't want to hand-edit, and it
    /// has no native UI of its own for switching back. The macOS menu bar
    /// entry (Carrel → Frontend → Use New Frontend) works but is invisible
    /// unless the user knows to look. This pill is the in-app escape hatch
    /// so a user can always get back to the new frontend without knowing
    /// about the menu.
    ///
    /// Only injected when the active frontend is `.legacy`; no-op for the
    /// new bundle. Self-contained: inline styles so legacy CSS can't stomp
    /// it, high z-index so it can't be covered, calls the existing
    /// `window.nativeFrontend.switch("new")` bridge on click.
    private func installLegacyEscapeHatchIfNeeded(_ webView: WKWebView) {
        // Use the coordinator's tracked active frontend rather than
        // FrontendSelector.resolved(). When a user clicks "Switch to new
        // frontend" via the pill, we explicitly load .new even though the
        // launch env var may still be "legacy" — resolved() would lie and
        // the pill would re-inject itself onto the new bundle. Using the
        // tracker mirrors what's actually on screen.
        guard activeFrontend == .legacy else {
            // Defensive cleanup: if a previous load injected the pill and
            // we just swapped to the new frontend, remove any leftover
            // instance. Harmless no-op when nothing's there.
            webView.evaluateJavaScript(
                "document.getElementById('__einstein_frontend_switch_pill')?.remove();",
                completionHandler: nil
            )
            return
        }
        let script = #"""
        (function () {
          if (document.getElementById('__einstein_frontend_switch_pill')) return;
          if (!window.nativeFrontend || typeof window.nativeFrontend.switch !== 'function') return;

          var pill = document.createElement('button');
          pill.id = '__einstein_frontend_switch_pill';
          pill.type = 'button';
          pill.textContent = '← Switch to new frontend';
          pill.setAttribute('aria-label', 'Switch to new frontend');
          pill.style.cssText = [
            'position:fixed',
            'top:14px',
            'right:14px',
            'z-index:2147483647',
            'display:inline-flex',
            'align-items:center',
            'gap:6px',
            'padding:8px 14px',
            'border-radius:999px',
            'border:1px solid rgba(255,255,255,0.18)',
            'background:rgba(18,22,28,0.88)',
            'color:#F4F2EC',
            'font:500 12px/1 -apple-system,BlinkMacSystemFont,"SF Pro Text",Helvetica,Arial,sans-serif',
            'letter-spacing:-0.005em',
            'cursor:pointer',
            'backdrop-filter:blur(12px)',
            '-webkit-backdrop-filter:blur(12px)',
            'box-shadow:0 6px 24px rgba(0,0,0,0.28)',
            'transition:transform 120ms ease-out, background-color 120ms ease-out'
          ].join(';');

          pill.addEventListener('mouseenter', function () {
            pill.style.background = 'rgba(24,28,36,0.96)';
            pill.style.transform = 'translateY(-1px)';
          });
          pill.addEventListener('mouseleave', function () {
            pill.style.background = 'rgba(18,22,28,0.88)';
            pill.style.transform = 'translateY(0)';
          });
          pill.addEventListener('click', function () {
            try { window.nativeFrontend.switch('new'); } catch (e) { console.error(e); }
          });

          if (document.body) {
            document.body.appendChild(pill);
          } else {
            document.addEventListener('DOMContentLoaded', function () {
              if (!document.getElementById('__einstein_frontend_switch_pill')) {
                document.body.appendChild(pill);
              }
            });
          }
        })();
        """#
        webView.evaluateJavaScript(script) { [weak self] _, error in
            if let error {
                self?.logger.error(
                    "Legacy escape-hatch injection failed: \(error.localizedDescription, privacy: .public)"
                )
            }
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        logger.error("Navigation failed: \(error.localizedDescription, privacy: .public)")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        logger.error("Provisional navigation failed: \(error.localizedDescription, privacy: .public)")
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }

        let shouldOpenExternally =
            navigationAction.navigationType == .linkActivated &&
            ["http", "https", "mailto"].contains(url.scheme?.lowercased() ?? "")

        if shouldOpenExternally {
            openExternal(url)
            decisionHandler(.cancel)
            return
        }

        decisionHandler(.allow)
    }

    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if let url = navigationAction.request.url {
            openExternal(url)
        }
        return nil
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptAlertPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping @MainActor @Sendable () -> Void
    ) {
        presentAlert(message: message).runModal()
        completionHandler()
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptConfirmPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping @MainActor @Sendable (Bool) -> Void
    ) {
        let alert = presentAlert(message: message)
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptTextInputPanelWithPrompt prompt: String,
        defaultText: String?,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping @MainActor @Sendable (String?) -> Void
    ) {
        let alert = presentAlert(message: prompt)
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")

        let textField = NSTextField(string: defaultText ?? "")
        textField.frame = NSRect(x: 0, y: 0, width: 320, height: 24)
        alert.accessoryView = textField

        let response = alert.runModal()
        completionHandler(response == .alertFirstButtonReturn ? textField.stringValue : nil)
    }

    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping @MainActor @Sendable ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection

        if let window = webView.window {
            panel.beginSheetModal(for: window) { response in
                completionHandler(response == .OK ? panel.urls : nil)
            }
            return
        }

        completionHandler(panel.runModal() == .OK ? panel.urls : nil)
    }
}

private enum BridgeError: LocalizedError {
    case unsupportedAction(String)

    var errorDescription: String? {
        switch self {
        case let .unsupportedAction(action):
            "Unsupported bridge action: \(action)"
        }
    }
}
