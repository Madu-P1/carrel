// swift-tools-version: 6.0

import PackageDescription

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
        )
    ]
)
