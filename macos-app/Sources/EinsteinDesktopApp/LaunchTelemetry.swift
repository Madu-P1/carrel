import Foundation
import OSLog

@MainActor
enum LaunchTelemetry {
    private static let logger = Logger(
        subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
        category: "launch"
    )
    private static var launchUptimeNanoseconds: UInt64?

    static func markLaunch() {
        let uptime = DispatchTime.now().uptimeNanoseconds
        launchUptimeNanoseconds = uptime
        emit(
            "launch-start uptime_ms=\(format(milliseconds: Double(uptime) / 1_000_000))"
        )
    }

    static func markInteractive(route: String, performanceNowMilliseconds: Double?) {
        let now = DispatchTime.now().uptimeNanoseconds
        let startedAt = launchUptimeNanoseconds

        let deltaMilliseconds = startedAt.map { Double(now - $0) / 1_000_000 } ?? 0
        let performanceLabel = performanceNowMilliseconds.map(format(milliseconds:)) ?? "n/a"
        emit(
            "app-interactive route=\(route) delta_ms=\(format(milliseconds: deltaMilliseconds)) perf_now_ms=\(performanceLabel)"
        )
    }

    private static func emit(_ message: String) {
        if let sink = _osLogSinkForTesting {
            sink(message)
        } else {
            logger.info("\(message, privacy: .public)")
        }
        if let data = "\(message)\n".data(using: .utf8) {
            FileHandle.standardError.write(data)
        }
    }

    /// Pure formatter for the duration values in the `launch-start`
    /// and `app-interactive` log lines. Two decimal places,
    /// locale-independent (no thousands separator). Non-finite
    /// inputs (NaN, ±Infinity) render as `n/a` so downstream log
    /// scrapers parsing `\d+\.\d{2}` aren't broken by edge-case
    /// callers — the marker functions don't produce non-finite
    /// values today, but `markInteractive(performanceNowMilliseconds:)`
    /// passes user-controllable numbers through the JS bridge.
    /// Exposed as `nonisolated` + internal so `@testable` can
    /// exercise it without forcing tests onto the main actor.
    nonisolated static func format(milliseconds: Double) -> String {
        guard milliseconds.isFinite else { return "n/a" }
        return String(format: "%.2f", milliseconds)
    }

    /// Test seam: read or override the `launchUptimeNanoseconds`
    /// field. Production code never touches this — it's exposed only
    /// so XCTest can reset between cases or seed a known anchor
    /// timestamp before calling `markInteractive`. Underscore prefix
    /// signals "internal-use only".
    static func _setLaunchUptimeForTesting(_ value: UInt64?) {
        launchUptimeNanoseconds = value
    }

    /// Test seam: replace the OSLog side of `emit(_:)` with a spy.
    /// When set, `logger.info` is bypassed and the closure is called
    /// with the exact message string instead. The stderr side
    /// (visible to log scrapers) always runs. Production code never
    /// sets this. Tests must reset to `nil` in `tearDown`.
    static var _osLogSinkForTesting: ((String) -> Void)?
}
