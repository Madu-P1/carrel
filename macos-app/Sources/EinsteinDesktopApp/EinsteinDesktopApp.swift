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
        // Floating companion is independent — it lives in its own
        // NSPanel above the Carrel window. Spawning it here keeps it
        // present from the moment the user sees Carrel come up. Setting
        // app activation policy to .regular before this so the panel
        // joins the user's space correctly.
        FloatingCompanionWindow.shared.start()
        appLogger.info(
            "Application finished launching (frontend=\(FrontendSelector.resolved().rawValue, privacy: .public))"
        )
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        // Closing the main Carrel window should NOT terminate the app —
        // the floating companion is intentionally outside the main
        // window's lifecycle. The user dismisses the companion via
        // its own mechanism (right-click menu, or Quit Carrel).
        false
    }

    func applicationWillTerminate(_ notification: Notification) {
        FloatingCompanionWindow.shared.stop()
        localCalendarBridge.stop()
        // BackendSupervisor also installs its own willTerminate
        // observer for SIGTERM delivery; calling stop() here is
        // belt-and-suspenders so the timer + observer both unwind.
        backendSupervisor.stop()
    }
}
