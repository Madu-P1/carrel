// swift-tools-version: 6.0

import PackageDescription

// Platform floor stays at macOS 14 for EinsteinDesktop and
// EinsteinIngestionBridge. EinsteinAFMBridge gates its Apple Foundation
// Models usage with @available(macOS 26.0, *) inside its source so the
// package still builds on macOS 14/15; the binary surfaces a
// macos_too_old error at runtime on those OS versions.
let package = Package(
    name: "EinsteinDesktop",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(
            name: "EinsteinDesktop",
            targets: ["EinsteinDesktop"]
        ),
        .executable(
            name: "EinsteinIngestionBridge",
            targets: ["EinsteinIngestionBridge"]
        ),
        .executable(
            name: "EinsteinAFMBridge",
            targets: ["EinsteinAFMBridge"]
        ),
        .executable(
            name: "EinsteinEncodeBridge",
            targets: ["EinsteinEncodeBridge"]
        )
    ],
    targets: [
        .executableTarget(
            name: "EinsteinDesktop",
            path: "Sources/EinsteinDesktopApp"
        ),
        .executableTarget(
            name: "EinsteinIngestionBridge",
            path: "Sources/EinsteinIngestionBridge"
        ),
        .executableTarget(
            name: "EinsteinAFMBridge",
            path: "Sources/EinsteinAFMBridge"
        ),
        .executableTarget(
            name: "EinsteinEncodeBridge",
            path: "Sources/EinsteinEncodeBridge"
        ),
        .testTarget(
            name: "EinsteinDesktopTests",
            dependencies: ["EinsteinDesktop"],
            path: "Tests/EinsteinDesktopTests"
        )
    ]
)
