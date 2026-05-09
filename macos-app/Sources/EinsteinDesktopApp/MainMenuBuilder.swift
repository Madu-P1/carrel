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
        appMenu.addItem(
            withTitle: "Quit \(appName)",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )

        appMenuItem.submenu = appMenu
        return appMenuItem
    }

    private static func buildFileMenu() -> NSMenuItem {
        let item = NSMenuItem()
        let menu = NSMenu(title: "File")
        menu.addItem(
            titled: "New Study Session",
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
        menu.addItem(NSMenuItem.separator())
        menu.addItem(
            titled: "Find in Reader",
            key: "f",
            command: "reader.find",
            target: MenuCommandDispatcher.shared
        )
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
        menu.addItem(
            titled: "Toggle Reader Focus Mode",
            key: "F",
            command: "reader.toggleFocusMode",
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
