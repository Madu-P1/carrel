import EventKit
import Foundation
import OSLog

// File-private logger so calls from background tasks don't have to
// hop to the main actor. Same pattern as BackendSupervisor.
private let calendarLog = Logger(
    subsystem: Bundle.main.bundleIdentifier ?? "com.madu.EinsteinDesktop",
    category: "calendar-bridge"
)

/// Reads the user's Apple Calendar (EventKit) and POSTs events to the
/// Carrel backend on launch + on every EKEventStoreChanged notification.
///
/// Why this exists: Carrel's plan/coach pipeline already supports HTTP
/// iCal feeds. Adding Apple Calendar via the same `calendar_feeds` row
/// shape (kind='local', synthetic URL `eventkit://local/{id}`) lets the
/// dashboard react to live calendar edits — the user moves a meeting
/// in Calendar.app, EventKit fires the change notification, this bridge
/// re-syncs, the backend's planner re-runs, the dashboard's React
/// Query refetch surfaces fresh suggestions.
///
/// Permission model: EventKit requires user consent. We request it
/// non-blocking on launch; until granted, the bridge stays idle. The
/// app's `NSCalendarsFullAccessUsageDescription` string in Info.plist
/// drives the prompt copy. Without that key the request silently
/// fails — surface that as a warning log so misconfiguration is
/// debuggable.
///
/// Failure modes that DON'T need to crash the app:
///   - Permission denied → log, stay idle. The user can grant access
///     later via System Settings > Privacy > Calendars.
///   - Backend offline → log + retry on next change. The supervisor
///     will respawn uvicorn; we don't try to coordinate.
///   - 90-day window has zero events → still POST (empty events =
///     "this calendar is now empty"; backend tombstones accordingly).
@MainActor
final class LocalCalendarBridge {
    /// Per-launch cap on how far ahead we sync. EventKit can return
    /// thousands of events on busy work calendars; bound the window
    /// to keep payloads sane and the planner's lookahead aligned with
    /// the existing iCal parser (`parse_ics` expands the same 90 days).
    private let lookaheadDays: TimeInterval = 90 * 24 * 60 * 60

    /// Backwards bound — past events still inform "I'm coming off three
    /// hours of meetings, schedule a recovery block" advice. Keep it
    /// modest so payloads stay small.
    private let lookbehindDays: TimeInterval = 7 * 24 * 60 * 60

    private let store = EKEventStore()
    private let session = URLSession(configuration: .ephemeral)

    /// Backend URL — same loopback the BackendSupervisor probes.
    private let syncURL = URL(string: "http://127.0.0.1:8000/api/calendar/local/sync")!

    /// Backend's local-API auth boundary. The middleware blocks every
    /// mutating /api/* request without `X-Carrel-Local-Token`. The
    /// frontend fetches the token via this endpoint at boot; we do
    /// the same and cache it for the lifetime of the bridge.
    private let tokenURL = URL(string: "http://127.0.0.1:8000/api/local-token")!
    private let localTokenHeader = "X-Carrel-Local-Token"
    private var cachedLocalToken: String?

    /// EKEventStoreChanged observer token — kept so we can remove on stop.
    private var changeObserver: NSObjectProtocol?

    /// Suppresses re-entrant syncs while one is in flight. EventKit can
    /// fire EKEventStoreChanged multiple times in quick succession during
    /// a Calendar.app drag-and-drop; coalesce them by ignoring fires
    /// while a sync is already running.
    private var syncInFlight = false

    /// Most recent sync timestamp; used by the debouncer below.
    private var lastSyncAt: Date?

    /// Minimum gap between syncs. EventKit notifications can arrive
    /// in bursts; 1 s is small enough that the user sees "live" while
    /// big enough to coalesce typical bursts.
    private let minSyncIntervalSeconds: TimeInterval = 1.0

    func start() {
        calendarLog.info("Starting local calendar bridge")
        Task { await self.requestAccessAndSync(reason: "launch") }
        installChangeObserver()
    }

    func stop() {
        if let observer = changeObserver {
            NotificationCenter.default.removeObserver(observer)
            changeObserver = nil
        }
    }

    // MARK: - Permission + sync

    private func requestAccessAndSync(reason: String) async {
        do {
            // requestFullAccessToEvents was added in macOS 14. The app's
            // minimum is 14, so we don't need the deprecated path.
            let granted = try await store.requestFullAccessToEvents()
            guard granted else {
                calendarLog.notice("Calendar access denied by user; bridge idle.")
                return
            }
            await runSync(reason: reason)
        } catch {
            calendarLog.error(
                "Calendar access request failed (\(reason, privacy: .public)): \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    private func runSync(reason: String) async {
        if syncInFlight {
            calendarLog.debug("Sync already in flight, skipping (\(reason, privacy: .public))")
            return
        }
        if let lastSyncAt, Date().timeIntervalSince(lastSyncAt) < minSyncIntervalSeconds {
            // Coalesce burst — let the next debounced fire pick it up.
            calendarLog.debug("Sync debounced (\(reason, privacy: .public))")
            return
        }
        syncInFlight = true
        defer { syncInFlight = false }
        lastSyncAt = Date()

        let calendars = store.calendars(for: .event)
        guard !calendars.isEmpty else {
            calendarLog.notice("No event calendars available; nothing to sync.")
            return
        }

        let now = Date()
        let start = now.addingTimeInterval(-lookbehindDays)
        let end = now.addingTimeInterval(lookaheadDays)

        for calendar in calendars {
            let predicate = store.predicateForEvents(
                withStart: start, end: end, calendars: [calendar]
            )
            let events = store.events(matching: predicate)
            let payload = encodeSyncPayload(calendar: calendar, events: events)
            await postSync(payload, calendarId: calendar.calendarIdentifier)
        }
    }

    // MARK: - Change observer

    private func installChangeObserver() {
        changeObserver = NotificationCenter.default.addObserver(
            forName: .EKEventStoreChanged,
            object: store,
            queue: .main
        ) { [weak self] _ in
            // Hop to MainActor for state access — the notification queue
            // is .main but Swift 6 wants the actor hop explicit.
            Task { @MainActor [weak self] in
                await self?.runSync(reason: "EKEventStoreChanged")
            }
        }
    }

    // MARK: - Encoding + transport

    private func encodeSyncPayload(calendar: EKCalendar, events: [EKEvent]) -> Data? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]

        let eventPayloads: [[String: Any]] = events.map { event in
            // EventKit's `calendarItemExternalIdentifier` is the stable
            // cross-launch UID we want — eventIdentifier changes on edit.
            // Fall back to eventIdentifier if external ID is unavailable
            // (some iCloud calendars omit it).
            let uid = event.calendarItemExternalIdentifier ?? event.eventIdentifier ?? UUID().uuidString
            let status: String
            switch event.status {
            case .canceled: status = "cancelled"
            case .tentative: status = "tentative"
            default: status = "confirmed"
            }
            var payload: [String: Any] = [
                "uid": uid,
                "summary": event.title ?? "",
                "start_at": formatter.string(from: event.startDate ?? Date()),
                "end_at": formatter.string(from: event.endDate ?? event.startDate ?? Date()),
                "all_day": event.isAllDay,
                "status": status,
            ]
            if let tz = event.timeZone?.identifier {
                payload["timezone"] = tz
            }
            if let location = event.location, !location.isEmpty {
                payload["location"] = location
            }
            return payload
        }

        var body: [String: Any] = [
            "calendar_identifier": calendar.calendarIdentifier,
            "label": calendar.title,
            "events": eventPayloads,
        ]
        if let colorHex = cgColorHexString(from: calendar.cgColor) {
            body["color"] = colorHex
        }

        do {
            return try JSONSerialization.data(withJSONObject: body, options: [])
        } catch {
            calendarLog.error("Failed to encode sync payload: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    private func cgColorHexString(from color: CGColor?) -> String? {
        guard let color, let components = color.components, components.count >= 3 else {
            return nil
        }
        let r = Int(round(components[0] * 255))
        let g = Int(round(components[1] * 255))
        let b = Int(round(components[2] * 255))
        return String(format: "#%02X%02X%02X", r, g, b)
    }

    /// Fetch + cache the local API token. The endpoint is unauthenticated
    /// (it has to be — the frontend bootstraps from it too). Returns nil
    /// when the backend isn't up yet; caller falls back to no-token,
    /// which will 403 but not crash. Next sync attempt retries.
    private func fetchLocalToken() async -> String? {
        if let cachedLocalToken { return cachedLocalToken }
        var request = URLRequest(url: tokenURL)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                return nil
            }
            let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            if let token = payload?["token"] as? String, !token.isEmpty {
                cachedLocalToken = token
                return token
            }
            return nil
        } catch {
            return nil
        }
    }

    private func postSync(_ data: Data?, calendarId: String) async {
        guard let data else { return }
        var request = URLRequest(url: syncURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = await fetchLocalToken() {
            request.setValue(token, forHTTPHeaderField: localTokenHeader)
        }
        request.httpBody = data

        do {
            let (_, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                // 403 means our cached token went stale (e.g. backend
                // restarted). Bust the cache so the next attempt
                // re-fetches.
                if code == 403 {
                    cachedLocalToken = nil
                }
                calendarLog.error(
                    "Local calendar sync failed (\(calendarId, privacy: .public)) status=\(code)"
                )
                return
            }
            calendarLog.info("Local calendar synced (\(calendarId, privacy: .public))")
        } catch {
            // Backend offline at launch is normal — the supervisor will
            // bring it up. We'll re-fire on the next EKEventStoreChanged.
            calendarLog.notice(
                "Local calendar POST error (\(calendarId, privacy: .public)): \(error.localizedDescription, privacy: .public)"
            )
        }
    }
}
