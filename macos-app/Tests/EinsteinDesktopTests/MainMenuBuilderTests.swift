import AppKit
import WebKit
import XCTest
@testable import EinsteinDesktop

@MainActor
final class MainMenuBuilderTests: XCTestCase {

    // MARK: - escapeForJSStringLiteral

    func test_escape_passes_plain_text_unchanged() {
        XCTAssertEqual(
            WebViewBridgeDispatcher.escapeForJSStringLiteral("nav.library"),
            "nav.library"
        )
    }

    func test_escape_doubles_a_single_backslash() {
        XCTAssertEqual(
            WebViewBridgeDispatcher.escapeForJSStringLiteral("a\\b"),
            "a\\\\b"
        )
    }

    func test_escape_backslashes_a_double_quote() {
        XCTAssertEqual(
            WebViewBridgeDispatcher.escapeForJSStringLiteral("say \"hi\""),
            "say \\\"hi\\\""
        )
    }

    func test_escape_handles_combined_backslash_and_quote() {
        // Order matters: backslashes are escaped FIRST, so the
        // escape-introduced backslashes don't get re-escaped. The
        // string `\"` becomes `\\\"` (literal: \\ followed by \").
        XCTAssertEqual(
            WebViewBridgeDispatcher.escapeForJSStringLiteral("\\\""),
            "\\\\\\\""
        )
    }

    func test_escape_is_not_idempotent_running_twice_double_escapes() {
        // Running escape twice on raw input must NOT collapse to the
        // single-pass result; documents that callers must not pass
        // a pre-escaped string back through. Uses raw-string syntax
        // so the literal counts are unambiguous.
        let input = #"a\b"# // raw: a, \, b
        let once = WebViewBridgeDispatcher.escapeForJSStringLiteral(input)
        XCTAssertEqual(once, #"a\\b"#, "First pass doubles the single backslash")

        let twice = WebViewBridgeDispatcher.escapeForJSStringLiteral(once)
        XCTAssertEqual(twice, #"a\\\\b"#, "Second pass doubles both backslashes again")
        XCTAssertNotEqual(twice, once, "Double-pass must not equal single-pass")
    }

    // MARK: - App menu

    func test_appMenu_has_about_hide_quit_with_separators() {
        let item = MainMenuBuilder.buildAppMenu()
        let menu = try? XCTUnwrap(item.submenu)
        XCTAssertNotNil(menu)
        guard let submenu = menu else { return }

        let titles = submenu.items.map(\.title)
        XCTAssertTrue(titles.contains(where: { $0.hasPrefix("About ") }))
        XCTAssertTrue(titles.contains(where: { $0.hasPrefix("Hide ") }))
        XCTAssertTrue(titles.contains("Hide Others"))
        XCTAssertTrue(titles.contains("Show All"))
        XCTAssertTrue(titles.contains(where: { $0.hasPrefix("Quit ") }))

        let separatorCount = submenu.items.filter(\.isSeparatorItem).count
        XCTAssertEqual(separatorCount, 2, "App menu should have exactly two separators (after About, before Quit)")
    }

    func test_appMenu_hide_others_uses_command_option_h() {
        let item = MainMenuBuilder.buildAppMenu()
        guard let submenu = item.submenu else { return XCTFail("appMenu has no submenu") }
        guard let hideOthers = submenu.items.first(where: { $0.title == "Hide Others" }) else {
            return XCTFail("Hide Others item missing")
        }
        XCTAssertEqual(hideOthers.keyEquivalent, "h")
        XCTAssertEqual(hideOthers.keyEquivalentModifierMask, [.command, .option])
    }

    func test_appMenu_quit_uses_command_q() {
        let item = MainMenuBuilder.buildAppMenu()
        guard let submenu = item.submenu else { return XCTFail("appMenu has no submenu") }
        guard let quit = submenu.items.first(where: { $0.title.hasPrefix("Quit ") }) else {
            return XCTFail("Quit item missing")
        }
        XCTAssertEqual(quit.keyEquivalent, "q")
        XCTAssertEqual(quit.action, #selector(NSApplication.terminate(_:)))
    }

    // MARK: - File menu

    func test_fileMenu_contains_new_import_close_print() {
        let item = MainMenuBuilder.buildFileMenu()
        guard let submenu = item.submenu else { return XCTFail("fileMenu has no submenu") }
        let titles = submenu.items.map(\.title)
        XCTAssertEqual(
            titles,
            ["New Study Session", "Import Source…", "", "Close Window", "Print…"],
            "File menu order/titles drifted; got: \(titles)"
        )
        XCTAssertTrue(submenu.items[2].isSeparatorItem)
    }

    func test_fileMenu_new_study_session_dispatches_file_new_command() {
        let item = MainMenuBuilder.buildFileMenu()
        guard let new = item.submenu?.items.first(where: { $0.title == "New Study Session" }) else {
            return XCTFail("New Study Session missing")
        }
        XCTAssertEqual(new.representedObject as? String, "file.new")
        XCTAssertEqual(new.keyEquivalent, "n")
        XCTAssertTrue(new.target === MenuCommandDispatcher.shared)
        XCTAssertEqual(new.action, #selector(MenuCommandDispatcher.dispatchCommand(_:)))
    }

    func test_fileMenu_import_dispatches_file_import_command() {
        let item = MainMenuBuilder.buildFileMenu()
        guard let imp = item.submenu?.items.first(where: { $0.title == "Import Source…" }) else {
            return XCTFail("Import Source missing")
        }
        XCTAssertEqual(imp.representedObject as? String, "file.import")
        XCTAssertEqual(imp.keyEquivalent, "i")
    }

    // MARK: - Edit menu

    func test_editMenu_contains_full_clipboard_set_plus_find() {
        let item = MainMenuBuilder.buildEditMenu()
        guard let submenu = item.submenu else { return XCTFail("editMenu has no submenu") }
        let titles = submenu.items.map(\.title)
        let nonSep = titles.filter { !$0.isEmpty }
        XCTAssertEqual(
            nonSep,
            ["Undo", "Redo", "Cut", "Copy", "Paste", "Select All", "Find in Reader"],
            "Edit menu items drifted; got: \(nonSep)"
        )
    }

    func test_editMenu_find_in_reader_dispatches_reader_find() {
        let item = MainMenuBuilder.buildEditMenu()
        guard let find = item.submenu?.items.first(where: { $0.title == "Find in Reader" }) else {
            return XCTFail("Find in Reader missing")
        }
        XCTAssertEqual(find.representedObject as? String, "reader.find")
        XCTAssertEqual(find.keyEquivalent, "f")
    }

    // MARK: - View menu

    func test_viewMenu_contains_toggles_zoom_and_pagination() {
        let item = MainMenuBuilder.buildViewMenu()
        guard let submenu = item.submenu else { return XCTFail("viewMenu has no submenu") }
        let commands = submenu.items.compactMap { $0.representedObject as? String }
        XCTAssertEqual(
            commands,
            [
                "view.toggleLeftSidebar",
                "view.toggleRightPanel",
                "view.toggleTheme",
                "reader.toggleFocusMode",
                "view.zoomIn",
                "view.zoomOut",
                "view.zoomReset",
                "reader.nextPage",
                "reader.prevPage",
            ],
            "View menu command order drifted; got: \(commands)"
        )
    }

    func test_viewMenu_toggle_right_panel_uses_command_option_b() {
        let item = MainMenuBuilder.buildViewMenu()
        guard let toggle = item.submenu?.items.first(where: {
            ($0.representedObject as? String) == "view.toggleRightPanel"
        }) else {
            return XCTFail("Toggle Right Panel missing")
        }
        XCTAssertEqual(toggle.keyEquivalent, "b")
        XCTAssertEqual(toggle.keyEquivalentModifierMask, [.command, .option])
    }

    func test_viewMenu_zoom_in_uses_command_equals() {
        let item = MainMenuBuilder.buildViewMenu()
        guard let zoom = item.submenu?.items.first(where: { $0.title == "Zoom In" }) else {
            return XCTFail("Zoom In missing")
        }
        XCTAssertEqual(zoom.keyEquivalent, "=")
    }

    func test_viewMenu_next_page_uses_right_arrow_function_key() {
        let item = MainMenuBuilder.buildViewMenu()
        guard let next = item.submenu?.items.first(where: { $0.title == "Next Page" }) else {
            return XCTFail("Next Page missing")
        }
        XCTAssertEqual(next.keyEquivalent, "\u{F703}", "Right-arrow function key (NSRightArrowFunctionKey)")
    }

    // MARK: - Navigate menu

    func test_navigateMenu_routes_in_order_with_numeric_shortcuts() {
        let item = MainMenuBuilder.buildNavigateMenu()
        guard let submenu = item.submenu else { return XCTFail("navigateMenu has no submenu") }

        let routeItems = submenu.items.filter { ($0.representedObject as? String)?.hasPrefix("nav.") == true }
        let routes = routeItems.map { ($0.representedObject as? String) ?? "" }
        XCTAssertEqual(
            routes,
            ["nav.dashboard", "nav.session", "nav.library", "nav.reader", "nav.ask", "nav.study"]
        )
        let keys = routeItems.map(\.keyEquivalent)
        XCTAssertEqual(keys, ["1", "2", "3", "4", "5", "6"])
    }

    func test_navigateMenu_command_palette_uses_command_k() {
        let item = MainMenuBuilder.buildNavigateMenu()
        guard let palette = item.submenu?.items.first(where: {
            ($0.representedObject as? String) == "palette.open"
        }) else {
            return XCTFail("Command Palette item missing")
        }
        XCTAssertEqual(palette.keyEquivalent, "k")
        XCTAssertEqual(palette.title, "Command Palette…")
    }

    // MARK: - Window menu

    func test_windowMenu_has_minimize_and_zoom() {
        let item = MainMenuBuilder.buildWindowMenu()
        guard let submenu = item.submenu else { return XCTFail("windowMenu has no submenu") }
        XCTAssertEqual(submenu.title, "Window")
        let titles = submenu.items.map(\.title)
        XCTAssertEqual(titles, ["Minimize", "Zoom"])

        XCTAssertEqual(submenu.items[0].keyEquivalent, "m")
        XCTAssertEqual(submenu.items[0].action, #selector(NSWindow.performMiniaturize(_:)))
        XCTAssertEqual(submenu.items[1].keyEquivalent, "")
    }

    // MARK: - Help menu

    func test_helpMenu_contains_keyboard_shortcuts() {
        let item = MainMenuBuilder.buildHelpMenu()
        guard let submenu = item.submenu else { return XCTFail("helpMenu has no submenu") }
        XCTAssertEqual(submenu.title, "Help")
        XCTAssertEqual(submenu.items.count, 1)

        let shortcuts = submenu.items[0]
        XCTAssertEqual(shortcuts.title, "Keyboard Shortcuts")
        XCTAssertEqual(shortcuts.keyEquivalent, "?")
        XCTAssertEqual(shortcuts.representedObject as? String, "help.shortcuts")
    }

    // MARK: - NSMenu.addItem(titled:key:command:modifiers:target:) helper

    func test_addItem_sets_title_key_command_modifiers_target_and_action() {
        let menu = NSMenu(title: "scratch")
        let target = NSObject()
        let result = menu.addItem(
            titled: "Test Item",
            key: "x",
            command: "test.command",
            modifiers: [.command, .shift],
            target: target
        )

        XCTAssertEqual(result.title, "Test Item")
        XCTAssertEqual(result.keyEquivalent, "x")
        XCTAssertEqual(result.keyEquivalentModifierMask, [.command, .shift])
        XCTAssertTrue(result.target === target)
        XCTAssertEqual(result.representedObject as? String, "test.command")
        XCTAssertEqual(result.action, #selector(MenuCommandDispatcher.dispatchCommand(_:)))
        XCTAssertEqual(menu.items.count, 1, "addItem should append exactly one NSMenuItem")
    }

    func test_addItem_defaults_modifier_mask_to_command_only() {
        let menu = NSMenu(title: "scratch")
        let result = menu.addItem(
            titled: "Default Mods",
            key: "y",
            command: "test.default",
            target: nil
        )
        XCTAssertEqual(result.keyEquivalentModifierMask, [.command])
    }

    // MARK: - install() integrates the seven submenus

    func test_install_attaches_seven_top_level_menus_in_expected_order() {
        // Swift Package test bundles don't auto-init NSApplication;
        // `NSApp` is an implicitly-unwrapped optional that's nil
        // until first reference. Touch `.shared` to force-init so
        // `NSApp.mainMenu = ...` inside install() doesn't crash.
        _ = NSApplication.shared

        let priorMainMenu = NSApp.mainMenu
        let priorWindowsMenu = NSApp.windowsMenu
        let priorHelpMenu = NSApp.helpMenu
        defer {
            NSApp.mainMenu = priorMainMenu
            NSApp.windowsMenu = priorWindowsMenu
            NSApp.helpMenu = priorHelpMenu
        }

        MainMenuBuilder.install()

        guard let mainMenu = NSApp.mainMenu else {
            return XCTFail("NSApp.mainMenu was not set by install()")
        }
        XCTAssertEqual(mainMenu.items.count, 7, "Expected exactly seven top-level menus")

        let titles = mainMenu.items.compactMap { $0.submenu?.title }
        XCTAssertEqual(
            titles,
            ["Carrel", "File", "Edit", "View", "Navigate", "Window", "Help"]
        )

        XCTAssertNotNil(NSApp.windowsMenu, "install() must wire NSApp.windowsMenu")
        XCTAssertEqual(NSApp.windowsMenu?.title, "Window")
        XCTAssertNotNil(NSApp.helpMenu, "install() must wire NSApp.helpMenu")
        XCTAssertEqual(NSApp.helpMenu?.title, "Help")
    }

    // MARK: - WebViewRegistry

    func test_webViewRegistry_starts_empty_or_holds_only_a_real_webview() {
        // Defensive: another test in this process may have registered
        // a WKWebView. Snapshot + restore so the assertion is robust
        // regardless of order.
        let prior = WebViewRegistry.current
        defer {
            if let prior {
                WebViewRegistry.register(prior)
            }
        }
        // After unregistering the snapshot, current must be nil even
        // if prior was non-nil — proves unregister actually clears.
        if let prior {
            WebViewRegistry.unregister(prior)
        }
        XCTAssertNil(WebViewRegistry.current)
    }

    func test_webViewRegistry_register_then_current_returns_it() {
        let prior = WebViewRegistry.current
        defer {
            if let prior {
                WebViewRegistry.register(prior)
            } else if let current = WebViewRegistry.current {
                WebViewRegistry.unregister(current)
            }
        }

        let webView = WKWebView(frame: .zero)
        WebViewRegistry.register(webView)
        XCTAssertTrue(WebViewRegistry.current === webView)
    }

    func test_webViewRegistry_unregister_only_clears_matching_webview() {
        let prior = WebViewRegistry.current
        defer {
            if let prior {
                WebViewRegistry.register(prior)
            } else if let current = WebViewRegistry.current {
                WebViewRegistry.unregister(current)
            }
        }

        let a = WKWebView(frame: .zero)
        let b = WKWebView(frame: .zero)
        WebViewRegistry.register(a)
        WebViewRegistry.unregister(b) // should be a no-op: b was never registered

        XCTAssertTrue(
            WebViewRegistry.current === a,
            "unregister with a non-matching webview must not clear current"
        )

        WebViewRegistry.unregister(a)
        XCTAssertNil(WebViewRegistry.current)
    }
}
