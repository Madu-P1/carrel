import XCTest
@testable import EinsteinDesktop

final class LocalApiTokenTests: XCTestCase {
    private var tempDirectory: URL!

    override func setUpWithError() throws {
        try super.setUpWithError()
        let base = FileManager.default.temporaryDirectory
        tempDirectory = base.appendingPathComponent(
            "LocalApiTokenTests-\(UUID().uuidString)",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: tempDirectory,
            withIntermediateDirectories: true
        )
    }

    override func tearDownWithError() throws {
        if let dir = tempDirectory, FileManager.default.fileExists(atPath: dir.path) {
            try FileManager.default.removeItem(at: dir)
        }
        tempDirectory = nil
        try super.tearDownWithError()
    }

    private func tokenURL(_ name: String = "local-api-token") -> URL {
        tempDirectory.appendingPathComponent(name, isDirectory: false)
    }

    private func posixMode(of url: URL) throws -> Int {
        let attrs = try FileManager.default.attributesOfItem(atPath: url.path)
        let raw = attrs[.posixPermissions] as? NSNumber
        return raw?.intValue ?? -1
    }

    func test_creates_new_token_file_when_missing() throws {
        let url = tokenURL()
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))

        let token = try LocalApiToken.resolveOrCreateToken(at: url)

        XCTAssertFalse(token.isEmpty)
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    }

    func test_generated_token_uses_urlsafe_base64_format() throws {
        let token = try LocalApiToken.resolveOrCreateToken(at: tokenURL())

        // 32 random bytes → 44-char base64 → 43 chars after stripping
        // one `=` of padding. Matches `secrets.token_urlsafe(32)`.
        XCTAssertEqual(token.count, 43)

        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        XCTAssertTrue(
            token.unicodeScalars.allSatisfy { allowed.contains($0) },
            "Token contains characters outside URL-safe base64 alphabet: \(token)"
        )
    }

    func test_persists_token_matching_returned_value() throws {
        let url = tokenURL()

        let returned = try LocalApiToken.resolveOrCreateToken(at: url)
        let onDisk = try String(contentsOf: url, encoding: .utf8)

        XCTAssertEqual(returned, onDisk)
    }

    func test_returns_same_token_across_repeated_calls() throws {
        let url = tokenURL()

        let first = try LocalApiToken.resolveOrCreateToken(at: url)
        let second = try LocalApiToken.resolveOrCreateToken(at: url)
        let third = try LocalApiToken.resolveOrCreateToken(at: url)

        XCTAssertEqual(first, second)
        XCTAssertEqual(second, third)
    }

    func test_generates_distinct_tokens_across_separate_files() throws {
        let a = try LocalApiToken.resolveOrCreateToken(at: tokenURL("token-a"))
        let b = try LocalApiToken.resolveOrCreateToken(at: tokenURL("token-b"))

        XCTAssertNotEqual(a, b, "Two fresh tokens collided — RNG sanity check failed")
    }

    func test_returns_existing_token_when_file_already_present() throws {
        let url = tokenURL()
        let preset = "preset-token-value-abc123"
        try preset.data(using: .utf8)!.write(to: url)

        let returned = try LocalApiToken.resolveOrCreateToken(at: url)

        XCTAssertEqual(returned, preset)
    }

    func test_trims_whitespace_from_existing_token() throws {
        let url = tokenURL()
        let padded = "  surrounded-by-whitespace  \n\t"
        try padded.data(using: .utf8)!.write(to: url)

        let returned = try LocalApiToken.resolveOrCreateToken(at: url)

        XCTAssertEqual(returned, "surrounded-by-whitespace")
    }

    func test_sets_owner_only_permissions_on_new_token() throws {
        let url = tokenURL()

        _ = try LocalApiToken.resolveOrCreateToken(at: url)

        XCTAssertEqual(try posixMode(of: url), 0o600)
    }

    func test_reasserts_owner_only_permissions_on_existing_file() throws {
        let url = tokenURL()
        let preset = "preset-token-value-xyz"
        try preset.data(using: .utf8)!.write(to: url)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o644],
            ofItemAtPath: url.path
        )
        XCTAssertEqual(try posixMode(of: url), 0o644)

        _ = try LocalApiToken.resolveOrCreateToken(at: url)

        XCTAssertEqual(try posixMode(of: url), 0o600)
    }

    func test_throws_malformed_when_existing_file_is_empty() throws {
        let url = tokenURL()
        try Data().write(to: url)

        XCTAssertThrowsError(try LocalApiToken.resolveOrCreateToken(at: url)) { error in
            guard case LocalApiTokenError.malformed = error else {
                XCTFail("Expected .malformed, got \(error)")
                return
            }
        }
    }

    func test_throws_malformed_when_existing_file_is_whitespace_only() throws {
        let url = tokenURL()
        try "   \n\t  ".data(using: .utf8)!.write(to: url)

        XCTAssertThrowsError(try LocalApiToken.resolveOrCreateToken(at: url)) { error in
            guard case LocalApiTokenError.malformed = error else {
                XCTFail("Expected .malformed on whitespace-only file, got \(error)")
                return
            }
        }
    }

    func test_throws_writeFailed_when_parent_directory_missing() {
        let url = tempDirectory
            .appendingPathComponent("missing-subdir", isDirectory: true)
            .appendingPathComponent("local-api-token", isDirectory: false)

        XCTAssertThrowsError(try LocalApiToken.resolveOrCreateToken(at: url)) { error in
            guard case LocalApiTokenError.writeFailed = error else {
                XCTFail("Expected .writeFailed when parent directory is missing, got \(error)")
                return
            }
        }
    }

    func test_tokenFileURL_creates_carrel_subdirectory_when_missing() throws {
        let carrelDir = tempDirectory.appendingPathComponent("Carrel", isDirectory: true)
        XCTAssertFalse(FileManager.default.fileExists(atPath: carrelDir.path))

        let url = try LocalApiToken.tokenFileURL(baseDirectory: tempDirectory)

        var isDir: ObjCBool = false
        XCTAssertTrue(FileManager.default.fileExists(atPath: carrelDir.path, isDirectory: &isDir))
        XCTAssertTrue(isDir.boolValue, "Carrel/ should be a directory")
        XCTAssertEqual(url.lastPathComponent, "local-api-token")
        XCTAssertEqual(url.deletingLastPathComponent().lastPathComponent, "Carrel")
    }

    func test_tokenFileURL_is_idempotent_when_carrel_subdirectory_exists() throws {
        let first = try LocalApiToken.tokenFileURL(baseDirectory: tempDirectory)
        let second = try LocalApiToken.tokenFileURL(baseDirectory: tempDirectory)

        XCTAssertEqual(first, second)
    }

    func test_tokenFileURL_throws_directoryCreateFailed_when_base_is_a_regular_file() throws {
        let blocker = tempDirectory.appendingPathComponent("blocker.txt", isDirectory: false)
        try Data("not a directory".utf8).write(to: blocker)

        XCTAssertThrowsError(try LocalApiToken.tokenFileURL(baseDirectory: blocker)) { error in
            guard case LocalApiTokenError.directoryCreateFailed = error else {
                XCTFail("Expected .directoryCreateFailed when base is a regular file, got \(error)")
                return
            }
        }
    }
}
