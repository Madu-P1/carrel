import Foundation
import XCTest
@testable import EinsteinDesktop

/// FrontendSelector decides which bundled HTML file the WKWebView
/// loads. Wrong choice = blank window, so the resolution order
/// matters: env var > UserDefaults > default.
final class FrontendSelectorTests: XCTestCase {
    func testBundledResourceForNew() {
        let res = FrontendSelector.bundledResource(for: .new)
        XCTAssertEqual(res.name, "app.new")
        XCTAssertEqual(res.ext, "html")
    }

    func testBundledResourceForLegacy() {
        let res = FrontendSelector.bundledResource(for: .legacy)
        XCTAssertEqual(res.name, "app.html")
        XCTAssertEqual(res.ext, "legacy")
    }

    func testFrontendEnumRoundTripsViaRawValue() {
        // The user-default key persists the rawValue; a typo here
        // means the user's pinned preference silently reverts to
        // .new on next launch.
        XCTAssertEqual(Frontend(rawValue: "new"), .new)
        XCTAssertEqual(Frontend(rawValue: "legacy"), .legacy)
        XCTAssertNil(Frontend(rawValue: "unknown"))
    }

    func testFrontendRawValueIsLowercase() {
        // FrontendSelector.resolved() lowercases env + UserDefaults
        // input before parsing. If the rawValues drifted to mixed
        // case, the lookup would silently fail.
        XCTAssertEqual(Frontend.new.rawValue, "new")
        XCTAssertEqual(Frontend.legacy.rawValue, "legacy")
    }
}
