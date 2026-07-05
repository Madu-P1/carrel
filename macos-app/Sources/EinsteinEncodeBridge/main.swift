// EinsteinEncodeBridge — on-device sentence encoder for Cachet (proposer-side).
//
// Wraps Apple's NLContextualEmbedding (NaturalLanguage): a transformer text
// encoder that runs FULLY on-device. No model ships in the bundle, no network
// is touched, and no user text leaves the machine — the zero-egress guarantee
// holds by construction, not by an env flag. The English contextual model is
// 512-dimensional (see `--dim`).
//
// This is a RECALL primitive only: it decides which source span the
// deterministic engine should check a claim against. It never renders a
// verdict; the deterministic verbatim/typed check remains the sole disposer.
// Design note: memory cachet-llm-adoption-proposer-side.
//
// Wire protocol (matches the EinsteinIngestionBridge / EinsteinAFMBridge
// precedent of a spawn-per-call stdin/stdout sidecar). Called by
// `services/retrieval/embeddings.py::AppleContextualEmbedder`:
//   * `--dim`  : print the embedding dimension as a bare integer, then exit 0.
//   * default  : read UTF-8 text from stdin, one item per line; write one JSON
//                array per line to stdout — the L2-normalized mean-pooled
//                embedding for that item, 1:1 with input lines. An empty or
//                unembeddable line yields a zero vector.
//
// Platform floor is macOS 14 (NLContextualEmbedding is macOS 14+), so this
// builds in the same `swift build` as the core targets with no macOS-26 gate.

import Foundation
import NaturalLanguage

guard let embedder = NLContextualEmbedding(language: .english) else {
    FileHandle.standardError.write(Data("EinsteinEncodeBridge: no English contextual-embedding model\n".utf8))
    exit(2)
}

if CommandLine.arguments.contains("--dim") {
    print(embedder.dimension)
    exit(0)
}

if !embedder.hasAvailableAssets {
    // Request the on-device model assets (a one-time OS-managed download) and
    // block until it settles. Re-query the property rather than capturing the
    // closure's result, which keeps the closure Sendable-clean under Swift 6.
    let semaphore = DispatchSemaphore(value: 0)
    embedder.requestAssets { _, _ in semaphore.signal() }
    _ = semaphore.wait(timeout: .now() + 120)
    if !embedder.hasAvailableAssets {
        FileHandle.standardError.write(Data("EinsteinEncodeBridge: model assets unavailable\n".utf8))
        exit(3)
    }
}

do {
    try embedder.load()
} catch {
    FileHandle.standardError.write(Data("EinsteinEncodeBridge: load failed: \(error.localizedDescription)\n".utf8))
    exit(3)
}

let dim = embedder.dimension

func encode(_ raw: String) -> [Double] {
    var pooled = [Double](repeating: 0, count: dim)
    let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    if text.isEmpty { return pooled }
    guard let result = try? embedder.embeddingResult(for: text, language: .english) else { return pooled }
    var tokenCount = 0
    result.enumerateTokenVectors(in: text.startIndex..<text.endIndex) { vector, _ in
        let count = min(vector.count, dim)
        for i in 0..<count { pooled[i] += vector[i] }
        tokenCount += 1
        return true
    }
    if tokenCount > 0 { for i in 0..<dim { pooled[i] /= Double(tokenCount) } }
    // L2-normalize so downstream cosine similarity is a plain dot product.
    var norm = 0.0
    for value in pooled { norm += value * value }
    norm = norm.squareRoot()
    if norm > 0 { for i in 0..<dim { pooled[i] /= norm } }
    return pooled
}

func emit(_ vector: [Double]) {
    var out = "["
    out.reserveCapacity(vector.count * 9)
    for (i, value) in vector.enumerated() {
        if i > 0 { out += "," }
        out += String(format: "%.6f", value)
    }
    out += "]"
    print(out)
}

while let line = readLine(strippingNewline: true) {
    emit(encode(line))
}
