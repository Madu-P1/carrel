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
        .windowToolbarStyle(.unifiedCompact(showsTitle: true))
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    /// Watches the FastAPI backend at 127.0.0.1:8000 and respawns it
    /// when missing. The backend is normally started by
    /// `script/build_and_run.sh::ensure_backend` before the .app
    /// boots, but the app shouldn't depend on that for liveness:
    /// closing the terminal that ran the script, a manual `pkill`,
    /// macOS power management, or just a crash all leave the .app
    /// running with a dead backend, and every API call silently
    /// fails. The supervisor closes that gap by probing /api/health
    /// on launch + every 60s and spawning uvicorn itself when the
    /// probe fails.
    private let backendSupervisor = BackendSupervisor()

    /// Bridges Apple Calendar (EventKit) into the Carrel backend so the
    /// dashboard re-runs coach advice when the user moves a meeting in
    /// Calendar.app. Requires NSCalendarsFullAccessUsageDescription in
    /// Info.plist; without it the EventKit prompt silently fails.
    private let localCalendarBridge = LocalCalendarBridge()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        MainMenuBuilder.install()
        LaunchTelemetry.markLaunch(frontend: FrontendSelector.resolved().rawValue)
        backendSupervisor.start()
        // Start the calendar bridge AFTER the backend supervisor so the
        // first sync attempt has a live target.
        localCalendarBridge.start()
        appLogger.info(
            "Application finished launching (frontend=\(FrontendSelector.resolved().rawValue, privacy: .public))"
        )
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        localCalendarBridge.stop()
        // BackendSupervisor also installs its own willTerminate
        // observer for SIGTERM delivery; calling stop() here is
        // belt-and-suspenders so the timer + observer both unwind.
        backendSupervisor.stop()
    }
}
