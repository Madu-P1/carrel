import AppKit
import WebKit

@MainActor
enum MainMenuBuilder {
    static func install() {
        let mainMenu = NSMenu(title: "MainMenu")

        mainMenu.addItem(buildAppMenu())
        mainMenu.addItem(buildFileMenu())
        mainMenu.addItem(buildEditMenu())
        mainMenu.addItem(buildViewMenu())
        mainMenu.addItem(buildNavigateMenu())
        mainMenu.addItem(buildWindowMenu())
        mainMenu.addItem(buildHelpMenu())

        NSApp.mainMenu = mainMenu
        NSApp.windowsMenu = mainMenu.item(withTitle: "Window")?.submenu
        NSApp.helpMenu = mainMenu.item(withTitle: "Help")?.submenu
    }

    private static func buildAppMenu() -> NSMenuItem {
        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu(title: "Carrel")

        let appName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Carrel"

        appMenu.addItem(
            withTitle: "About \(appName)",
            action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)),
            keyEquivalent: ""
        )
        appMenu.addItem(
            titled: "Preferences…",
            key: ",",
            command: "app.preferences",
            target: MenuCommandDispatcher.shared
        )
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(
            withTitle: "Hide \(appName)",
            action: #selector(NSApplication.hide(_:)),
            keyEquivalent: "h"
        )
        appMenu.addItem(
            withTitle: "Hide Others",
            action: #selector(NSApplication.hideOtherApplications(_:)),
            keyEquivalent: "h"
        ).keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(
            withTitle: "Show All",
            action: #selector(NSApplication.unhideAllApplications(_:)),
            keyEquivalent: ""
        )
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(buildFrontendSwitcherItem())
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(
            withTitle: "Quit \(appName)",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )

        appMenuItem.submenu = appMenu
        return appMenuItem
    }

    /// Carrel > Frontend submenu. Lets the user flip between the new shell
    /// and the legacy `app.html` without dropping to the terminal. Works in
    /// both frontends because it's a native AppKit target/action, not a
    /// web-bridge command.
    private static func buildFrontendSwitcherItem() -> NSMenuItem {
        let container = NSMenuItem(title: "Frontend", action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: "Frontend")

        let newItem = NSMenuItem(
            title: "Use New Frontend",
            action: #selector(FrontendSwitchHandler.switchFrontend(_:)),
            keyEquivalent: ""
        )
        newItem.target = FrontendSwitchHandler.shared
        newItem.representedObject = Frontend.new.rawValue
        submenu.addItem(newItem)

        let legacyItem = NSMenuItem(
            title: "Use Legacy Frontend",
            action: #selector(FrontendSwitchHandler.switchFrontend(_:)),
            keyEquivalent: ""
        )
        legacyItem.target = FrontendSwitchHandler.shared
        legacyItem.representedObject = Frontend.legacy.rawValue
        submenu.addItem(legacyItem)

        container.submenu = submenu
        return container
    }

    private static func buildFileMenu() -> NSMenuItem {
        let item = NSMenuItem()
        let menu = NSMenu(title: "File")
        menu.addItem(
            titled: "New Workspace",
            key: "n",
            command: "file.new",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(
            titled: "Import Source…",
            key: "i",
            command: "file.import",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(NSMenuItem.separator())
        menu.addItem(
            withTitle: "Close Window",
            action: #selector(NSWindow.performClose(_:)),
            keyEquivalent: "w"
        )
        menu.addItem(
            withTitle: "Print…",
            action: Selector(("print:")),
            keyEquivalent: "p"
        )
        item.submenu = menu
        return item
    }

    private static func buildEditMenu() -> NSMenuItem {
        let item = NSMenuItem()
        let menu = NSMenu(title: "Edit")
        menu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        menu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        menu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        menu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        menu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        item.submenu = menu
        return item
    }

    private static func buildViewMenu() -> NSMenuItem {
        let item = NSMenuItem()
        let menu = NSMenu(title: "View")
        menu.addItem(
            titled: "Toggle Left Sidebar",
            key: "b",
            command: "view.toggleLeftSidebar",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(
            titled: "Toggle Right Panel",
            key: "b",
            command: "view.toggleRightPanel",
            modifiers: [.command, .option],
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(
            titled: "Toggle Theme",
            key: "T",
            command: "view.toggleTheme",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(NSMenuItem.separator())
        menu.addItem(
            titled: "Zoom In",
            key: "=",
            command: "view.zoomIn",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(
            titled: "Zoom Out",
            key: "-",
            command: "view.zoomOut",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(
            titled: "Actual Size",
            key: "0",
            command: "view.zoomReset",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(
            titled: "Next Page",
            key: "\u{F703}",
            command: "reader.nextPage",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(
            titled: "Previous Page",
            key: "\u{F702}",
            command: "reader.prevPage",
            target: MenuCommandDispatcher.shared
        )
        item.submenu = menu
        return item
    }

    private static func buildNavigateMenu() -> NSMenuItem {
        let item = NSMenuItem()
        let menu = NSMenu(title: "Navigate")
        menu.addItem(titled: "Dashboard", key: "1", command: "nav.dashboard", target: MenuCommandDispatcher.shared)
        menu.addItem(titled: "Session", key: "2", command: "nav.session", target: MenuCommandDispatcher.shared)
        menu.addItem(titled: "Library", key: "3", command: "nav.library", target: MenuCommandDispatcher.shared)
        menu.addItem(titled: "Reader", key: "4", command: "nav.reader", target: MenuCommandDispatcher.shared)
        menu.addItem(titled: "Ask", key: "5", command: "nav.ask", target: MenuCommandDispatcher.shared)
        menu.addItem(titled: "Study", key: "6", command: "nav.study", target: MenuCommandDispatcher.shared)
        menu.addItem(NSMenuItem.separator())
        menu.addItem(
            titled: "Command Palette…",
            key: "k",
            command: "palette.open",
            target: MenuCommandDispatcher.shared
        )
        item.submenu = menu
        return item
    }

    private static func buildWindowMenu() -> NSMenuItem {
        let item = NSMenuItem()
        let menu = NSMenu(title: "Window")
        menu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        menu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        item.submenu = menu
        return item
    }

    private static func buildHelpMenu() -> NSMenuItem {
        let item = NSMenuItem()
        let menu = NSMenu(title: "Help")
        menu.addItem(
            titled: "Keyboard Shortcuts",
            key: "?",
            command: "help.shortcuts",
            target: MenuCommandDispatcher.shared
        )
        menu.addItem(
            titled: "Carrel Help",
            key: "",
            command: "help.open",
            target: MenuCommandDispatcher.shared
        )
        item.submenu = menu
        return item
    }
}

@MainActor
final class MenuCommandDispatcher: NSObject {
    static let shared = MenuCommandDispatcher()

    @objc func dispatchCommand(_ sender: NSMenuItem) {
        guard let command = sender.representedObject as? String else {
            return
        }

        if !WebViewBridgeDispatcher.dispatch(command: command) {
            NSSound.beep()
        }
    }
}

/// Handles the native Carrel > Frontend submenu.
///
/// Two items, one per Frontend case, sharing this target. Clicking an item
/// persists the user's choice via FrontendSelector, then triggers a reload
/// on the current WKWebView by calling back into its Coordinator. No web
/// bridge involved, so this works from both the new and legacy frontends.
///
/// validateMenuItem puts a checkmark on the currently-active choice so the
/// user can see which bundle is loaded without having to remember.
@MainActor
final class FrontendSwitchHandler: NSObject, NSMenuItemValidation {
    static let shared = FrontendSwitchHandler()

    /// Tracks the frontend currently loaded in the WKWebView, independent of
    /// FrontendSelector.resolved(). resolved() honors the EINSTEIN_FRONTEND
    /// launch env var, which we deliberately want to override when the user
    /// clicks a menu item. Without this, clicks got silently no-op'd because
    /// resolved() kept returning the env value.
    private var activeFrontend: Frontend = FrontendSelector.resolved()

    @objc func switchFrontend(_ sender: NSMenuItem) {
        guard
            let raw = sender.representedObject as? String,
            let frontend = Frontend(rawValue: raw)
        else {
            NSSound.beep()
            return
        }

        // If the user is already on the requested frontend, do nothing (and
        // don't beep — a repeat click is a common accident, not a failure).
        if activeFrontend == frontend {
            return
        }

        FrontendSelector.setUserPreference(frontend)

        guard let webView = WebViewBridgeDispatcher.resolveCurrentWebView() else {
            NSSound.beep()
            return
        }

        if let coordinator = webView.navigationDelegate as? Coordinator {
            coordinator.loadBundledApp(into: webView, explicitFrontend: frontend)
            activeFrontend = frontend
        } else {
            NSSound.beep()
        }
    }

    func validateMenuItem(_ menuItem: NSMenuItem) -> Bool {
        guard
            let raw = menuItem.representedObject as? String,
            let frontend = Frontend(rawValue: raw)
        else {
            return true
        }
        menuItem.state = (frontend == activeFrontend) ? .on : .off
        return true
    }
}

enum WebViewBridgeDispatcher {
    @MainActor
    static func dispatch(command: String) -> Bool {
        guard let webView = resolveWebView() else {
            return false
        }

        let escaped = command
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")

        webView.evaluateJavaScript("window.__dispatchNativeMenu?.(\"\(escaped)\")") { _, error in
            if let error {
                NSLog("Carrel menu dispatch failed: %@", error.localizedDescription)
            }
        }
        return true
    }

    @MainActor
    private static func resolveWebView() -> WKWebView? {
        resolveCurrentWebView()
    }

    /// Public variant used by native-only handlers (e.g. FrontendSwitchHandler)
    /// that need direct access to the current WKWebView without going through
    /// the JS command bus.
    @MainActor
    static func resolveCurrentWebView() -> WKWebView? {
        if let keyWindow = NSApp.keyWindow, let webView = findWebView(in: keyWindow.contentView) {
            return webView
        }
        return WebViewRegistry.current
    }

    @MainActor
    private static func findWebView(in view: NSView?) -> WKWebView? {
        guard let view else {
            return nil
        }

        if let webView = view as? WKWebView {
            return webView
        }

        for subview in view.subviews {
            if let webView = findWebView(in: subview) {
                return webView
            }
        }

        return nil
    }
}

@MainActor
enum WebViewRegistry {
    private static weak var currentWebView: WKWebView?

    static var current: WKWebView? {
        currentWebView
    }

    static func register(_ webView: WKWebView) {
        currentWebView = webView
    }

    static func unregister(_ webView: WKWebView) {
        guard currentWebView === webView else {
            return
        }

        currentWebView = nil
    }
}

private extension NSMenu {
    @discardableResult
    func addItem(
        titled title: String,
        key: String,
        command: String,
        modifiers: NSEvent.ModifierFlags = [.command],
        target: AnyObject?
    ) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: #selector(MenuCommandDispatcher.dispatchCommand(_:)), keyEquivalent: key)
        item.keyEquivalentModifierMask = modifiers
        item.target = target
        item.representedObject = command
        addItem(item)
        return item
    }
}
