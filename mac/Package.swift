// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Hive",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "Hive", path: "Sources/Hive")
    ]
)
