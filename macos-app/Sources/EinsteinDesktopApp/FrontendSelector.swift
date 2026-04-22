import Foundation

enum Frontend: String {
    case legacy
    case new
}

/// Selects which bundled frontend the WKWebView should load.
///
/// Precedence (highest first):
///   1. `EINSTEIN_FRONTEND` process env var — for dev + scripts.
///   2. `com.madu.EinsteinDesktop.frontend` user default — user-set in-app toggle.
///   3. Default: `.new`.
enum FrontendSelector {
    private static let userDefaultsKey = "com.madu.EinsteinDesktop.frontend"

    static func resolved() -> Frontend {
        let raw = ProcessInfo.processInfo.environment["EINSTEIN_FRONTEND"]?.lowercased() ?? ""
        if let fromEnv = Frontend(rawValue: raw) {
            return fromEnv
        }
        let stored = UserDefaults.standard.string(forKey: userDefaultsKey)?.lowercased() ?? ""
        if let fromStore = Frontend(rawValue: stored) {
            return fromStore
        }
        return .new
    }

    /// Persist a user preference for which frontend to load. Takes effect on
    /// the next `loadBundledApp` invocation. Env-var overrides still win.
    static func setUserPreference(_ frontend: Frontend) {
        UserDefaults.standard.set(frontend.rawValue, forKey: userDefaultsKey)
    }

    static func bundledResource() -> (name: String, ext: String) {
        bundledResource(for: resolved())
    }

    /// Variant that skips env/UserDefaults resolution — used when a caller
    /// (e.g. the Frontend menu) has already decided which bundle to load.
    static func bundledResource(for frontend: Frontend) -> (name: String, ext: String) {
        switch frontend {
        case .new:
            return ("app.new", "html")
        case .legacy:
            return ("app.html", "legacy")
        }
    }
}
