import AppKit
import Foundation
import ImageIO
import PDFKit
import UniformTypeIdentifiers
import Vision

struct PDFPagePayload: Codable {
    let page: Int
    let text: String
    let used_ocr: Bool
    let native_char_count: Int
    let ocr_char_count: Int
}

struct BridgePayload: Codable {
    let parser: String
    let extraction_modes: [String]
    let warnings: [String]
    let confidence: Double
    let page_count: Int?
    let pages: [PDFPagePayload]?
    let text: String?
    let metadata: [String: String]?
}

enum BridgeError: Error {
    case invalidInput
    case unreadableFile
    case unsupportedType
}

func normalize(_ value: String) -> String {
    value
        .replacingOccurrences(of: "\r\n", with: "\n")
        .replacingOccurrences(of: "\r", with: "\n")
        .replacingOccurrences(of: #"[ \t]+"#, with: " ", options: .regularExpression)
        .replacingOccurrences(of: #"\n{3,}"#, with: "\n\n", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

/// PDFKit's `PDFPage.string` usually emits proper inter-word spaces, but
/// some PDFs (certain academic publishers, some LaTeX output) draw glyphs
/// with explicit positioning and never emit space characters at all, so
/// the text layer comes back as "ofeventsconfrontingmanagers". For those
/// space-deprived pages this re-derives word spaces from the horizontal
/// gaps between glyph bounds.
///
/// It is deliberately conservative. Pages whose text layer already has a
/// normal share of spaces are returned untouched: `characterBounds`
/// reading order is not always consistent with `page.string` order (slide
/// and title layers scatter glyph positions, and even "135/2009" can
/// report a phantom 34pt gap mid-number), so geometry is only trusted
/// where the alternative — a jammed, spaceless text layer — is already
/// unusable. Newlines are never synthesised; `page.string`'s own newlines
/// and character order are kept.
func extractPageText(_ page: PDFPage) -> String {
    guard let raw = page.string, !raw.isEmpty else { return "" }
    let charCount = page.numberOfCharacters
    let ns = raw as NSString
    // characterBounds(at:) indexes the same space as the page string;
    // bail to the raw string if PDFKit disagrees on the length.
    guard charCount > 0, ns.length == charCount else { return raw }

    // Gate: only space-deprived pages get geometry reconstruction. Normal
    // English prose runs ~13-18% spaces; a broken text layer is far below
    // that. A conservative 4% floor leaves every well-formed page exactly
    // as `page.string` returned it, so the common case can never regress.
    var spaceCount = 0
    for scalar in raw.unicodeScalars where scalar == " " {
        spaceCount += 1
    }
    guard Double(spaceCount) / Double(charCount) < 0.04 else { return raw }

    var result = String()
    result.reserveCapacity(ns.length + ns.length / 6)
    var prev = CGRect.null

    for i in 0..<charCount {
        let ch = ns.substring(with: NSRange(location: i, length: 1))
        let isWhitespace = ch.rangeOfCharacter(from: .whitespacesAndNewlines) != nil
        let bounds = page.characterBounds(at: i)
        let hasGeometry = !bounds.isNull && !bounds.isInfinite

        if !isWhitespace, hasGeometry, !prev.isNull,
           let last = result.last, !last.isWhitespace {
            // Two glyphs share a visual line when their vertical extents
            // overlap. Comparing midY is wrong: glyph boxes vary with
            // ascenders and descenders, so even "o" next to "n" can have
            // different midYs on one line.
            let verticalOverlap = min(prev.maxY, bounds.maxY) - max(prev.minY, bounds.minY)
            let minHeight = min(prev.height, bounds.height)
            let heightScale = max(prev.height, bounds.height)
            let sameLine = minHeight > 0 && verticalOverlap > minHeight * 0.4
            let gap = bounds.minX - prev.maxX
            // A word space is a meaningful fraction of the font size;
            // intra-word kerning and tracking are much tighter.
            if sameLine, heightScale > 0, gap > heightScale * 0.25 {
                result.append(" ")
            }
        }
        result.append(ch)
        if hasGeometry {
            prev = bounds
        }
    }
    return result
}

func cgImage(from image: NSImage) -> CGImage? {
    var proposedRect = NSRect(origin: .zero, size: image.size)
    if let cgImage = image.cgImage(forProposedRect: &proposedRect, context: nil, hints: nil) {
        return cgImage
    }
    guard let data = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: data) else {
        return nil
    }
    return bitmap.cgImage
}

func recognizeText(in cgImage: CGImage) throws -> String {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    // Academic and technical sources are dense with domain jargon and
    // proper nouns that Vision's language model would "correct" toward
    // common dictionary words. Raw recognition is more faithful here.
    request.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])
    let lines = request.results?
        .compactMap { $0.topCandidates(1).first?.string }
        .map(normalize)
        .filter { !$0.isEmpty } ?? []
    return lines.joined(separator: "\n")
}

func imagePayload(url: URL) throws -> BridgePayload {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw BridgeError.unreadableFile
    }
    let text = normalize(try recognizeText(in: cgImage))
    var metadata: [String: String] = [:]
    if let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] {
        if let pixelWidth = properties[kCGImagePropertyPixelWidth] {
            metadata["pixel_width"] = String(describing: pixelWidth)
        }
        if let pixelHeight = properties[kCGImagePropertyPixelHeight] {
            metadata["pixel_height"] = String(describing: pixelHeight)
        }
    }
    return BridgePayload(
        parser: "apple-vision-image",
        extraction_modes: ["ocr"],
        warnings: text.isEmpty ? ["Vision OCR did not find readable text in this image."] : [],
        confidence: text.isEmpty ? 0.28 : 0.74,
        page_count: 1,
        pages: nil,
        text: text,
        metadata: metadata.isEmpty ? nil : metadata
    )
}

func pdfPayload(url: URL) throws -> BridgePayload {
    guard let document = PDFDocument(url: url) else {
        throw BridgeError.unreadableFile
    }
    var warnings: [String] = []
    var pages: [PDFPagePayload] = []
    var extractionModes = Set<String>(["native_text"])
    var ocrPages = 0

    for index in 0..<document.pageCount {
        guard let page = document.page(at: index) else { continue }
        let nativeText = normalize(extractPageText(page))
        var ocrText = ""
        var usedOCR = false
        if nativeText.count < 80 {
            let thumbnail = page.thumbnail(of: NSSize(width: 2000, height: 2600), for: .mediaBox)
            if let pageImage = cgImage(from: thumbnail) {
                ocrText = normalize((try? recognizeText(in: pageImage)) ?? "")
                if !ocrText.isEmpty {
                    extractionModes.insert("ocr")
                }
            }
        }
        let finalText: String
        if nativeText.isEmpty && !ocrText.isEmpty {
            finalText = ocrText
            usedOCR = true
        } else if !ocrText.isEmpty && ocrText.count > max(nativeText.count + 40, Int(Double(nativeText.count) * 1.6)) {
            finalText = ocrText
            usedOCR = true
        } else {
            finalText = nativeText
        }
        if usedOCR {
            ocrPages += 1
        }
        if finalText.isEmpty {
            warnings.append("Page \(index + 1) produced no readable text.")
        }
        pages.append(
            PDFPagePayload(
                page: index + 1,
                text: finalText,
                used_ocr: usedOCR,
                native_char_count: nativeText.count,
                ocr_char_count: ocrText.count
            )
        )
    }

    if ocrPages > 0 {
        warnings.append("OCR was used on \(ocrPages) PDF page(s).")
    }

    let combined = pages.map(\.text).filter { !$0.isEmpty }.joined(separator: "\n\n")
    let confidence = combined.isEmpty ? 0.25 : (ocrPages > 0 ? 0.82 : 0.92)
    return BridgePayload(
        parser: "apple-pdfkit-vision",
        extraction_modes: Array(extractionModes).sorted(),
        warnings: warnings,
        confidence: confidence,
        page_count: document.pageCount,
        pages: pages,
        text: combined,
        metadata: nil
    )
}

func payload(for url: URL) throws -> BridgePayload {
    let ext = url.pathExtension.lowercased()
    if ext == "pdf" {
        return try pdfPayload(url: url)
    }
    if let type = UTType(filenameExtension: ext),
       type.conforms(to: .image) {
        return try imagePayload(url: url)
    }
    throw BridgeError.unsupportedType
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys]

do {
    guard CommandLine.arguments.count >= 2 else {
        throw BridgeError.invalidInput
    }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let result = try payload(for: url)
    let data = try encoder.encode(result)
    FileHandle.standardOutput.write(data)
} catch BridgeError.invalidInput {
    fputs("Usage: EinsteinIngestionBridge <path>\n", stderr)
    exit(64)
} catch BridgeError.unreadableFile {
    fputs("Unreadable file\n", stderr)
    exit(66)
} catch BridgeError.unsupportedType {
    fputs("Unsupported type\n", stderr)
    exit(65)
} catch {
    fputs("Bridge failure: \(error)\n", stderr)
    exit(70)
}
