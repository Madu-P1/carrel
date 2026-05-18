import XCTest
@testable import EinsteinDesktop

final class UploadMimeTypesTests: XCTestCase {
    func test_pdf_maps_to_application_pdf() {
        let url = URL(fileURLWithPath: "/tmp/document.pdf")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url), "application/pdf")
    }

    func test_epub_maps_to_application_epub_zip() {
        let url = URL(fileURLWithPath: "/tmp/book.epub")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url), "application/epub+zip")
    }

    func test_txt_maps_to_text_plain() {
        let url = URL(fileURLWithPath: "/tmp/notes.txt")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url), "text/plain")
    }

    func test_md_and_markdown_both_map_to_text_markdown() {
        let mdUrl = URL(fileURLWithPath: "/tmp/readme.md")
        let markdownUrl = URL(fileURLWithPath: "/tmp/spec.markdown")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: mdUrl), "text/markdown")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: markdownUrl), "text/markdown")
    }

    func test_html_and_htm_both_map_to_text_html() {
        let htmlUrl = URL(fileURLWithPath: "/tmp/page.html")
        let htmUrl = URL(fileURLWithPath: "/tmp/page.htm")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: htmlUrl), "text/html")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: htmUrl), "text/html")
    }

    func test_docx_maps_to_wordprocessingml_document() {
        let url = URL(fileURLWithPath: "/tmp/draft.docx")
        XCTAssertEqual(
            UploadMimeTypes.mimeType(for: url),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    }

    func test_unknown_extension_falls_through_to_octet_stream() {
        let url = URL(fileURLWithPath: "/tmp/mystery.xyz")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url), "application/octet-stream")
    }

    func test_extension_lookup_is_case_insensitive() {
        let upperUrl = URL(fileURLWithPath: "/tmp/REPORT.PDF")
        let mixedUrl = URL(fileURLWithPath: "/tmp/Slides.HtMl")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: upperUrl), "application/pdf")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: mixedUrl), "text/html")
    }

    func test_file_with_no_extension_falls_through() {
        let url = URL(fileURLWithPath: "/tmp/README")
        XCTAssertEqual(UploadMimeTypes.mimeType(for: url), "application/octet-stream")
    }
}
