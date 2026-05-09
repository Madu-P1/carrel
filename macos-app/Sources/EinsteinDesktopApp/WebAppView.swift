import AppKit
import OSLog
import SwiftUI
import WebKit

struct WebAppView: NSViewRepresentable {
    var onLoadPhaseChange: (WebAppLoadPhase) -> Void = { _ in }

    func makeCoordinator() -> Coordinator {
        Coordinator(onLoadPhaseChange: onLoadPhaseChange)
    }

    func makeNSView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: NativeBridge.storageHandlerName)
        contentController.add(context.coordinator, name: NativeBridge.externalOpenHandlerName)
        contentController.add(context.coordinator, name: NativeBridge.menuHandlerName)
        contentController.add(context.coordinator, name: NativeBridge.telemetryHandlerName)
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
        // default. `allowFileAccessFromFileURLs` (narrow scope —
        // same-file-origin) is needed so ES dynamic imports like
        // `import("./pdf.js")` inside the bundled app can reach sibling
        // file:// chunks without being rejected as cross-origin.
        //
        // Security posture: the bundled HTML is a first-party artifact we
        // ship in the app. User-uploaded PDFs are parsed by pdf.js as data
        // and rendered to canvas/text layers; they are never loaded as HTML
        // documents, so they cannot exploit this file:// loosening.
        // `tests/bundle-integrity.test.ts` blocks any third-party host
        // references at build time to keep the local-first promise.
        configuration.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator

        #if DEBUG
        if #available(macOS 13.3, *) {
            webView.isInspectable = true
        }
        #endif

        context.coordinator.attach(to: webView)
        context.coordinator.loadBundledApp(into: webView)

        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
        context.coordinator.onLoadPhaseChange = onLoadPhaseChange
    }

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
        WebViewRegistry.unregister(nsView)
    }
}

@MainActor
final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler, WKUIDelegate {
    private weak var webView: WKWebView?
    private var didLogInteractive = false
    var onLoadPhaseChange: (WebAppLoadPhase) -> Void
    private let logger = Logger(
        subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
        category: "webview"
    )

    init(onLoadPhaseChange: @escaping (WebAppLoadPhase) -> Void) {
        self.onLoadPhaseChange = onLoadPhaseChange
        super.init()
    }

    func attach(to webView: WKWebView) {
        self.webView = webView
        WebViewRegistry.register(webView)
    }

    /// Load the bundled web app.
    func loadBundledApp(into webView: WKWebView) {
        onLoadPhaseChange(.loading)
        didLogInteractive = false
        guard let htmlURL = Bundle.main.url(forResource: "app.new", withExtension: "html") else {
            logger.error("Missing bundled HTML resource app.new.html")
            onLoadPhaseChange(.failed("The bundled frontend resource was not found inside the app."))
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

        // loadFileURL so relative asset paths (./assets.new/index.css,
        // ./assets.new/instrument-serif-latin-400.woff2, the pdf.js chunk)
        // resolve correctly against the Resources directory under file://.
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
        default:
            logger.warning("Unhandled script message: \(message.name, privacy: .public)")
        }
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
        let scheme = url.scheme ?? "unknown"
        let host = url.host ?? "unknown"
        logger.info("Opening external URL scheme=\(scheme, privacy: .public) host=\(host, privacy: .public)")
        NSWorkspace.shared.open(url)
    }

    private func presentAlert(message: String, style: NSAlert.Style = .informational) -> NSAlert {
        let alert = NSAlert()
        alert.alertStyle = style
        alert.messageText = "Carrel"
        alert.informativeText = message
        return alert
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        onLoadPhaseChange(.loading)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        logger.info("Finished loading bundled web app")
        onLoadPhaseChange(.ready)
        probeInteractiveMarker()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        logger.error("Navigation failed: \(error.localizedDescription, privacy: .public)")
        onLoadPhaseChange(.failed(error.localizedDescription))
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        logger.error("Provisional navigation failed: \(error.localizedDescription, privacy: .public)")
        onLoadPhaseChange(.failed(error.localizedDescription))
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
