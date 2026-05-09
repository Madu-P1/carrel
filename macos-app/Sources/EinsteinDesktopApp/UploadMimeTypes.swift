import Foundation

/// Best-effort MIME type lookup for files dropped on the floating
/// companion. The backend's `/api/jobs/import` ingest accepts the
/// types listed here; anything else falls through to
/// `application/octet-stream` and the parser layer figures it out.
///
/// Lifted to a free function so it can be unit-tested without
/// instantiating the FloatingCompanionWindow (which depends on AppKit
/// and a backend URL).
enum UploadMimeTypes {
    static func mimeType(for url: URL) -> String {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "pdf": return "application/pdf"
        case "epub": return "application/epub+zip"
        case "txt": return "text/plain"
        case "md", "markdown": return "text/markdown"
        case "html", "htm": return "text/html"
        case "docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        default: return "application/octet-stream"
        }
    }
}
