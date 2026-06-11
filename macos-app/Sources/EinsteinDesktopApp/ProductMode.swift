import Foundation

/// Which product this bundle is: Carrel (the study app) or Cachet (the
/// verification product). Decided at bundle-assembly time, not compile
/// time: script/build_and_run.sh writes `CarrelProductMode` into the
/// generated Info.plist (`--cachet` flag), so one compiled binary serves
/// both products and product identity lives entirely in the bundle.
/// Absent or unrecognized key means Carrel, so existing bundles are
/// unchanged.
enum ProductMode {
    case carrel
    case cachet

    static let current: ProductMode = {
        let raw = Bundle.main.object(forInfoDictionaryKey: "CarrelProductMode") as? String
        return raw?.lowercased() == "cachet" ? .cachet : .carrel
    }()

    var displayName: String {
        switch self {
        case .carrel: return "Carrel"
        case .cachet: return "Cachet"
        }
    }
}
