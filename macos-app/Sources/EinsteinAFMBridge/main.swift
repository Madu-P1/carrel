// EinsteinAFMBridge
//
// Standalone Swift CLI that wraps Apple's FoundationModels framework
// for use by Carrel's Python backend (ai/afm_client.py).
//
// Wire protocol:
//   stdin:  one JSON object matching BridgeRequest
//   stdout: one JSON object matching BridgeResponse, line-terminated
//   stderr: human-readable diagnostic on protocol errors
//
// Exit codes:
//   0   request handled, ok=true
//   1   request handled, ok=false (Python reads error_code)
//   64  invalid JSON on stdin (bridge_protocol_error)
//   70  encoding failure or other internal bridge error
//
// Mirrors the EinsteinIngestionBridge pattern. macOS 14 build still
// succeeds (the @available gate keeps Apple Foundation Models out of
// reach on older OS); at runtime on macOS 14/15 the binary returns a
// macos_too_old error and exits 1 so Python can fall back cleanly.
//
// Request kinds:
//   availability        -- probe SystemLanguageModel.default.availability
//   request_text        -- free-form text generation (legacy, low-trust)
//   request_json        -- free-form text + Python-side JSON parse (legacy)
//   request_tool_call   -- free-form text + Python-side schema parse (legacy)
//   request_grounded_answer -- @Generable GroundedAnswer (PREFERRED for tutor)
//
// The @Generable path uses Apple's guided generation: the decoder is
// token-constrained against the Swift struct so the model literally
// cannot emit a shape that doesn't decode. This is the AFM equivalent
// of Ollama's `format` parameter or Claude's tool-use. Use it for any
// flow that needs reliable structured output.

import Foundation

#if canImport(FoundationModels)
import FoundationModels
#endif

// MARK: - Wire types

struct BridgeRequest: Codable {
    let kind: String
    let requestId: String
    let system: String?
    let prompt: String?
    let maxTokens: Int?
    // 0.0 = greedy / deterministic. Used for grounded answers; nil for legacy paths.
    let temperature: Double?

    enum CodingKeys: String, CodingKey {
        case kind
        case requestId = "request_id"
        case system
        case prompt
        case maxTokens = "max_tokens"
        case temperature
    }
}

struct BridgeResponse: Codable {
    let ok: Bool
    let requestId: String
    let kind: String
    let text: String?
    // For @Generable paths: the structured payload encoded as JSON
    // (Python will decode it). Mutually exclusive with `text` in
    // practice; either field can be nil.
    let structured: BridgeStructuredPayload?
    let model: String?
    let inputTokens: Int?
    let outputTokens: Int?
    let latencyMs: Double
    let stopReason: String?
    let errorCode: String?
    let errorMessage: String?
    let availabilityState: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case requestId = "request_id"
        case kind
        case text
        case structured
        case model
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case latencyMs = "latency_ms"
        case stopReason = "stop_reason"
        case errorCode = "error_code"
        case errorMessage = "error_message"
        case availabilityState = "availability_state"
    }
}

// MARK: - Structured payloads for @Generable paths

/// Discriminated union of structured payloads emitted by guided-generation
/// kinds. Python decodes by inspecting `kind` on the parent response.
struct BridgeStructuredPayload: Codable {
    let groundedAnswer: GroundedAnswerPayload?

    enum CodingKeys: String, CodingKey {
        case groundedAnswer = "grounded_answer"
    }
}

struct GroundedAnswerPayload: Codable {
    let answer: String
    let supportingChunks: [Int]
    let unsupportedClaims: [String]

    enum CodingKeys: String, CodingKey {
        case answer
        case supportingChunks = "supporting_chunks"
        case unsupportedClaims = "unsupported_claims"
    }
}

// MARK: - @Generable types (the actual guided-generation schemas)
//
// One Swift type per Carrel task. The macro generates the decoding
// constraints; the model cannot emit a value that fails to decode.
// Keep these types narrow: only fields that benefit from constrained
// decoding. Anything that's better computed server-side (e.g.
// verbatim quotes, source page numbers, citation chip rendering) is
// NOT included here, by design.

#if canImport(FoundationModels)

@available(macOS 26.0, *)
@Generable
struct GroundedAnswer {
    @Guide(description: "Answer the question using only facts from the chunks. Do not name any company, person, ticker, or number that is not in the chunks. If the chunks do not directly answer the question, return an empty answer.")
    let answer: String

    @Guide(description: "1-based chunk numbers whose text you used to write the answer. Empty list if you could not ground the answer in any chunk.")
    let supportingChunks: [Int]

    @Guide(description: "Parts of the question the chunks do not cover. Use this when the chunks compute something the question asks to define, or vice versa.")
    let unsupportedClaims: [String]
}

#endif

// MARK: - Encoder/decoder

private let encoder: JSONEncoder = {
    let enc = JSONEncoder()
    enc.outputFormatting = [.sortedKeys]
    return enc
}()

private let decoder = JSONDecoder()

// MARK: - Response helpers

private func errorResponse(
    requestId: String,
    kind: String,
    code: String,
    message: String,
    latencyMs: Double = 0,
    availabilityState: String? = nil
) -> BridgeResponse {
    return BridgeResponse(
        ok: false,
        requestId: requestId,
        kind: kind,
        text: nil,
        structured: nil,
        model: "afm-3b",
        inputTokens: nil,
        outputTokens: nil,
        latencyMs: latencyMs,
        stopReason: nil,
        errorCode: code,
        errorMessage: message,
        availabilityState: availabilityState
    )
}

private func writeOut(_ resp: BridgeResponse) {
    do {
        let data = try encoder.encode(resp)
        FileHandle.standardOutput.write(data)
        if let newline = "\n".data(using: .utf8) {
            FileHandle.standardOutput.write(newline)
        }
    } catch {
        FileHandle.standardError.write(
            "Encoding failure: \(error)\n".data(using: .utf8) ?? Data()
        )
        exit(70)
    }
}

// MARK: - Foundation Models handler (gated to macOS 26+)

#if canImport(FoundationModels)

@available(macOS 26.0, *)
private func availabilityStateString() -> String {
    switch SystemLanguageModel.default.availability {
    case .available:
        return "available"
    case .unavailable(.deviceNotEligible):
        return "device_not_eligible"
    case .unavailable(.appleIntelligenceNotEnabled):
        return "apple_intelligence_not_enabled"
    case .unavailable(.modelNotReady):
        return "model_not_ready"
    @unknown default:
        return "unknown"
    }
}

@available(macOS 26.0, *)
private func makeSession(systemPrompt: String?) -> LanguageModelSession {
    if let sys = systemPrompt, !sys.isEmpty {
        return LanguageModelSession(instructions: Instructions { sys })
    }
    return LanguageModelSession()
}

@available(macOS 26.0, *)
private func generationOptions(temperature: Double?) -> GenerationOptions {
    // Greedy sampling = deterministic, which is what we want for
    // grounded factual answers. Caller can pass a temperature > 0 for
    // creative tasks (e.g. flashcard generation in a future request kind).
    if let t = temperature, t > 0 {
        return GenerationOptions(temperature: t)
    }
    return GenerationOptions(sampling: .greedy)
}

@available(macOS 26.0, *)
private func handleFreeFormText(_ req: BridgeRequest, start: Date) async -> BridgeResponse {
    let session = makeSession(systemPrompt: req.system)
    let userPrompt = req.prompt ?? ""
    do {
        let response = try await session.respond(
            to: userPrompt,
            options: generationOptions(temperature: req.temperature)
        )
        let elapsed = Date().timeIntervalSince(start) * 1000.0
        let generated = String(describing: response.content)
        return BridgeResponse(
            ok: true,
            requestId: req.requestId,
            kind: req.kind,
            text: generated,
            structured: nil,
            model: "afm-3b",
            inputTokens: nil,
            outputTokens: nil,
            latencyMs: elapsed,
            stopReason: "stop",
            errorCode: nil,
            errorMessage: nil,
            availabilityState: nil
        )
    } catch {
        let elapsed = Date().timeIntervalSince(start) * 1000.0
        return errorResponse(
            requestId: req.requestId,
            kind: req.kind,
            code: "afm_generation_failed",
            message: String(describing: error),
            latencyMs: elapsed
        )
    }
}

@available(macOS 26.0, *)
private func handleGroundedAnswer(_ req: BridgeRequest, start: Date) async -> BridgeResponse {
    let session = makeSession(systemPrompt: req.system)
    let userPrompt = req.prompt ?? ""
    do {
        let response = try await session.respond(
            to: userPrompt,
            generating: GroundedAnswer.self,
            includeSchemaInPrompt: false,
            options: generationOptions(temperature: req.temperature)
        )
        let elapsed = Date().timeIntervalSince(start) * 1000.0
        let content = response.content
        let payload = GroundedAnswerPayload(
            answer: content.answer,
            supportingChunks: content.supportingChunks,
            unsupportedClaims: content.unsupportedClaims
        )
        return BridgeResponse(
            ok: true,
            requestId: req.requestId,
            kind: req.kind,
            text: nil,
            structured: BridgeStructuredPayload(groundedAnswer: payload),
            model: "afm-3b",
            inputTokens: nil,
            outputTokens: nil,
            latencyMs: elapsed,
            stopReason: "stop",
            errorCode: nil,
            errorMessage: nil,
            availabilityState: nil
        )
    } catch {
        let elapsed = Date().timeIntervalSince(start) * 1000.0
        return errorResponse(
            requestId: req.requestId,
            kind: req.kind,
            code: "afm_generation_failed",
            message: String(describing: error),
            latencyMs: elapsed
        )
    }
}

@available(macOS 26.0, *)
private func handle(_ req: BridgeRequest) async -> BridgeResponse {
    let start = Date()

    if req.kind == "availability" {
        let state = availabilityStateString()
        let elapsed = Date().timeIntervalSince(start) * 1000.0
        return BridgeResponse(
            ok: state == "available",
            requestId: req.requestId,
            kind: req.kind,
            text: nil,
            structured: nil,
            model: "afm-3b",
            inputTokens: nil,
            outputTokens: nil,
            latencyMs: elapsed,
            stopReason: nil,
            errorCode: state == "available" ? nil : state,
            errorMessage: nil,
            availabilityState: state
        )
    }

    // Refuse generation if the model is not available right now.
    let state = availabilityStateString()
    guard state == "available" else {
        let elapsed = Date().timeIntervalSince(start) * 1000.0
        return errorResponse(
            requestId: req.requestId,
            kind: req.kind,
            code: state,
            message: "Apple Foundation Models is not available: \(state).",
            latencyMs: elapsed,
            availabilityState: state
        )
    }

    switch req.kind {
    case "request_grounded_answer":
        return await handleGroundedAnswer(req, start: start)
    case "request_text", "request_json", "request_tool_call":
        return await handleFreeFormText(req, start: start)
    default:
        let elapsed = Date().timeIntervalSince(start) * 1000.0
        return errorResponse(
            requestId: req.requestId,
            kind: req.kind,
            code: "unknown_kind",
            message: "Bridge does not handle kind: \(req.kind)",
            latencyMs: elapsed
        )
    }
}

#endif

// MARK: - Entry point

let stdinData = FileHandle.standardInput.readDataToEndOfFile()

guard let req = try? decoder.decode(BridgeRequest.self, from: stdinData) else {
    FileHandle.standardError.write(
        "Invalid request JSON on stdin\n".data(using: .utf8) ?? Data()
    )
    exit(64)
}

#if canImport(FoundationModels)
if #available(macOS 26.0, *) {
    let resp = await handle(req)
    writeOut(resp)
    exit(resp.ok ? 0 : 1)
} else {
    let resp = errorResponse(
        requestId: req.requestId,
        kind: req.kind,
        code: "macos_too_old",
        message: "Apple Foundation Models requires macOS 26 or newer."
    )
    writeOut(resp)
    exit(1)
}
#else
let resp = errorResponse(
    requestId: req.requestId,
    kind: req.kind,
    code: "foundation_models_unavailable",
    message: "FoundationModels framework not available in this build."
)
writeOut(resp)
exit(1)
#endif
