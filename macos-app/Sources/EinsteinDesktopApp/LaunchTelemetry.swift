import Foundation
import OSLog

@MainActor
enum LaunchTelemetry {
    private static let logger = Logger(
        subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
        category: "launch"
    )
    private static var launchUptimeNanoseconds: UInt64?

    static func markLaunch(frontend: String) {
        let uptime = DispatchTime.now().uptimeNanoseconds
        launchUptimeNanoseconds = uptime
        emit(
            "launch-start frontend=\(frontend) uptime_ms=\(format(milliseconds: Double(uptime) / 1_000_000))"
        )
    }

    static func markInteractive(frontend: String, route: String, performanceNowMilliseconds: Double?) {
        let now = DispatchTime.now().uptimeNanoseconds
        let startedAt = launchUptimeNanoseconds

        let deltaMilliseconds = startedAt.map { Double(now - $0) / 1_000_000 } ?? 0
        let performanceLabel = performanceNowMilliseconds.map(format(milliseconds:)) ?? "n/a"
        emit(
            "app-interactive frontend=\(frontend) route=\(route) delta_ms=\(format(milliseconds: deltaMilliseconds)) perf_now_ms=\(performanceLabel)"
        )
    }

    private static func emit(_ message: String) {
        logger.info("\(message, privacy: .public)")
        if let data = "\(message)\n".data(using: .utf8) {
            FileHandle.standardError.write(data)
        }
    }

    private static func format(milliseconds: Double) -> String {
        String(format: "%.2f", milliseconds)
    }
}
