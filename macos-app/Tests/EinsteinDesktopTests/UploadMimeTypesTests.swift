import Foundation
import XCTest
@testable import EinsteinDesktop

/// MIME-type lookup is the floating companion's contract with the
/// backend ingest endpoint. A misidentified extension means the
/// parser layer either rejects or routes to the wrong adapter, so
/// pin the mappings here.
final class UploadMimeTypesTests: XCTestCase {
    private func url(_ path: String) -> URL {
        URL(fileURLWithPath: path)
    }

    func testPdfMapsToApplicationPdf() {
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/notes.pdf")), "application/pdf")
    }

    func testEpubMapsToApplicationEpubZip() {
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/book.epub")), "application/epub+zip")
    }

    func testTxtMapsToTextPlain() {
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/lecture.txt")), "text/plain")
    }

    func testMarkdownMapsToTextMarkdown() {
        // Both common extensions resolve to the same MIME.
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/notes.md")), "text/markdown")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/notes.markdown")), "text/markdown")
    }

    func testHtmlMapsToTextHtml() {
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/x.html")), "text/html")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/x.htm")), "text/html")
    }

    func testDocxMapsToOpenXmlWordDocument() {
        XCTAssertEqual(
            UploadMimeTypes.mimeType(for: url("/tmp/paper.docx")),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    }

    func testExtensionMatchIsCaseInsensitive() {
        // macOS preserves case in path extensions; uppercase from
        // Finder shouldn't fall through to octet-stream.
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/SCAN.PDF")), "application/pdf")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url("/tmp/Book.ePub")), "application/epub+zip")
    }

    func testUnknownExtensionFallsThroughToOctetStream() {
        XCTAssertEqual(
            UploadMimeTypes.mimeType(for: url("/tmp/payload.xyz")),
            "application/octet-stream"
        )
    }

    func testNoExtensionFallsThroughToOctetStream() {
        XCTAssertEqual(
            UploadMimeTypes.mimeType(for: url("/tmp/extensionless")),
            "application/octet-stream"
        )
    }
}
