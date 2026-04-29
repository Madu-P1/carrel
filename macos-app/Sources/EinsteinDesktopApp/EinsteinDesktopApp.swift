import AppKit
import OSLog
import SwiftUI

private let appLogger = Logger(
    subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
    category: "app"
)

@main
struct EinsteinDesktopApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup("Carrel") {
            ContentView()
                .frame(minWidth: 1100, minHeight: 720)
        }
        .defaultSize(width: 1440, height: 920)
    }
}

struct ContentView: View {
    var body: some View {
        WebAppView()
            .background(Color.black)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        MainMenuBuilder.install()
        LaunchTelemetry.markLaunch(frontend: FrontendSelector.resolved().rawValue)
        appLogger.info(
            "Application finished launching (frontend=\(FrontendSelector.resolved().rawValue, privacy: .public))"
        )
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}
