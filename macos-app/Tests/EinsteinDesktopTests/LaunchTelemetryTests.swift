import Darwin
import XCTest
@testable import EinsteinDesktop

/// dup2-based stderr capture used by the marker-function tests
/// below. `LaunchTelemetry.emit(_:)` writes to `FileHandle.standardError`
/// which goes through fd 2; we replace fd 2 with the write end of a
/// `Pipe()` for the duration of the test and read what was emitted on
/// `finish()`. The original fd 2 is restored before reading so a test
/// assertion failure can still print its diagnostic to the real
/// terminal.
private final class StderrCapture {
    private let pipe: Pipe
    private let savedStderr: Int32

    init() {
        pipe = Pipe()
        savedStderr = dup(STDERR_FILENO)
        dup2(pipe.fileHandleForWriting.fileDescriptor, STDERR_FILENO)
    }

    func finish() -> String {
        // Restore original stderr first so subsequent failure logs
        // travel to the real terminal, not into the soon-closed pipe.
        dup2(savedStderr, STDERR_FILENO)
        close(savedStderr)
        // Close write end so the read side observes EOF.
        try? pipe.fileHandleForWriting.close()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        try? pipe.fileHandleForReading.close()
        return String(data: data, encoding: .utf8) ?? ""
    }
}

@MainActor
final class LaunchTelemetryTests: XCTestCase {
    override func setUp() {
        super.setUp()
        LaunchTelemetry._setLaunchUptimeForTesting(nil)
    }

    override func tearDown() {
        LaunchTelemetry._setLaunchUptimeForTesting(nil)
        super.tearDown()
    }

    // MARK: - format(milliseconds:)

    func test_format_returns_two_decimal_places_for_integer_input() {
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: 123), "123.00")
    }

    func test_format_returns_two_decimal_places_for_zero() {
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: 0), "0.00")
    }

    func test_format_rounds_to_two_decimal_places() {
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: 12.3456), "12.35")
    }

    func test_format_truncates_excess_precision() {
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: 0.001), "0.00")
    }

    func test_format_handles_negative_values() {
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: -5.5), "-5.50")
    }

    func test_format_handles_large_values_without_thousands_separator() {
        let formatted = LaunchTelemetry.format(milliseconds: 1_000_000.5)
        XCTAssertEqual(formatted, "1000000.50")
        XCTAssertFalse(
            formatted.contains(","),
            "Locale-independent output must not insert thousands separators"
        )
        XCTAssertFalse(
            formatted.contains(" "),
            "Locale-independent output must not insert thin-space separators"
        )
    }

    func test_format_preserves_two_trailing_zeros() {
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: 250), "250.00")
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: 7.1), "7.10")
    }

    func test_format_renders_typical_cold_launch_envelope() {
        // Carrel's cold-launch p50 target is ≤ 800ms; current p50 is
        // ~465ms (per CLAUDE.md "Benchmarks + budgets"). Spot-check
        // both ends of that envelope produce well-formed output that
        // downstream log scrapers can parse as a fixed-point millisecond
        // count.
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: 465.0), "465.00")
        XCTAssertEqual(LaunchTelemetry.format(milliseconds: 799.99), "799.99")
    }

    // MARK: - markLaunch()

    func test_markLaunch_emits_launch_start_with_uptime_ms() {
        let capture = StderrCapture()
        LaunchTelemetry.markLaunch()
        let output = capture.finish()

        XCTAssertNotNil(
            output.range(of: #"launch-start uptime_ms=\d+\.\d{2}"#, options: .regularExpression),
            "Expected `launch-start uptime_ms=N.NN`, got: \(output)"
        )
    }

    func test_markLaunch_terminates_line_with_newline() {
        let capture = StderrCapture()
        LaunchTelemetry.markLaunch()
        let output = capture.finish()

        XCTAssertTrue(
            output.hasSuffix("\n"),
            "emit() always appends \\n so log scrapers can split on lines; got: \(output)"
        )
    }

    // MARK: - markInteractive(route:performanceNowMilliseconds:)

    func test_markInteractive_without_prior_markLaunch_uses_zero_delta() {
        // launchUptimeNanoseconds is nil (reset in setUp); the
        // `startedAt.map { ... } ?? 0` branch should produce
        // delta_ms=0.00.
        let capture = StderrCapture()
        LaunchTelemetry.markInteractive(route: "/test", performanceNowMilliseconds: nil)
        let output = capture.finish()

        XCTAssertTrue(
            output.contains("delta_ms=0.00"),
            "Expected delta_ms=0.00 fallback when markLaunch never ran, got: \(output)"
        )
    }

    func test_markInteractive_with_nil_perf_now_renders_n_slash_a() {
        LaunchTelemetry._setLaunchUptimeForTesting(0)
        let capture = StderrCapture()
        LaunchTelemetry.markInteractive(route: "/r", performanceNowMilliseconds: nil)
        let output = capture.finish()

        XCTAssertTrue(
            output.contains("perf_now_ms=n/a"),
            "Expected perf_now_ms=n/a fallback when performance.now is unavailable, got: \(output)"
        )
    }

    func test_markInteractive_formats_perf_now_when_provided() {
        LaunchTelemetry._setLaunchUptimeForTesting(0)
        let capture = StderrCapture()
        LaunchTelemetry.markInteractive(route: "/route-2", performanceNowMilliseconds: 42.5)
        let output = capture.finish()

        XCTAssertTrue(
            output.contains("perf_now_ms=42.50"),
            "Expected perf_now_ms=42.50, got: \(output)"
        )
    }

    func test_markInteractive_includes_route_in_output() {
        LaunchTelemetry._setLaunchUptimeForTesting(0)
        let capture = StderrCapture()
        LaunchTelemetry.markInteractive(route: "/library", performanceNowMilliseconds: 100)
        let output = capture.finish()

        XCTAssertTrue(
            output.contains("route=/library"),
            "Expected route=/library in output, got: \(output)"
        )
    }

    func test_markLaunch_then_markInteractive_produces_positive_delta() {
        LaunchTelemetry.markLaunch()

        // Busy-wait briefly so DispatchTime advances measurably past
        // the markLaunch timestamp. 1ms is well within the resolution
        // of the system clock.
        let spinStart = DispatchTime.now().uptimeNanoseconds
        while DispatchTime.now().uptimeNanoseconds - spinStart < 1_000_000 { /* 1ms */ }

        let capture = StderrCapture()
        LaunchTelemetry.markInteractive(route: "/r", performanceNowMilliseconds: nil)
        let output = capture.finish()

        XCTAssertNotNil(
            output.range(of: #"delta_ms=\d+\.\d{2}"#, options: .regularExpression),
            "Expected delta_ms=N.NN, got: \(output)"
        )
        XCTAssertFalse(
            output.contains("delta_ms=0.00"),
            "Expected positive delta_ms after 1ms busy-wait, got: \(output)"
        )
    }

    func test_markInteractive_emits_app_interactive_line_terminated_by_newline() {
        let capture = StderrCapture()
        LaunchTelemetry.markInteractive(route: "/r", performanceNowMilliseconds: 1.0)
        let output = capture.finish()

        XCTAssertTrue(output.contains("app-interactive"), "Expected app-interactive prefix, got: \(output)")
        XCTAssertTrue(output.hasSuffix("\n"), "Expected trailing newline, got: \(output)")
    }
}
