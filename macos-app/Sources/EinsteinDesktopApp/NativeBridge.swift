enum NativeBridge {
    static let storageHandlerName = "nativeStorage"
    static let externalOpenHandlerName = "externalOpen"
    static let menuHandlerName = "nativeMenu"
    static let telemetryHandlerName = "nativeTelemetry"
    static let calendarHandlerName = "nativeCalendar"
    static let companionHandlerName = "nativeCompanion"

    static let bootstrapScript = #"""
    (() => {
      if (window.__einsteinDesktopBridgeInstalled) return;
      window.__einsteinDesktopBridgeInstalled = true;

      const callbacks = new Map();
      let nextId = 1;

      const postMessage = (handler, payload) => {
        const bridge = window.webkit?.messageHandlers?.[handler];
        if (!bridge) {
          throw new Error(`Missing native bridge: ${handler}`);
        }
        bridge.postMessage(payload);
      };

      window.__nativeStorageResolve = (id, payload) => {
        const callback = callbacks.get(id);
        if (!callback) return;
        callbacks.delete(id);
        callback.resolve(payload);
      };

      window.__nativeStorageReject = (id, error) => {
        const callback = callbacks.get(id);
        if (!callback) return;
        callbacks.delete(id);
        callback.reject(new Error(error?.message || "Native storage error"));
      };

      if (!window.storage) {
        window.storage = {
          get(key) {
            return new Promise((resolve, reject) => {
              const id = nextId++;
              callbacks.set(id, { resolve, reject });
              try {
                postMessage("nativeStorage", { id, action: "get", key });
              } catch (error) {
                callbacks.delete(id);
                reject(error);
              }
            });
          },
          set(key, value) {
            return new Promise((resolve, reject) => {
              const id = nextId++;
              callbacks.set(id, { resolve, reject });
              try {
                postMessage("nativeStorage", { id, action: "set", key, value });
              } catch (error) {
                callbacks.delete(id);
                reject(error);
              }
            });
          }
        };
      }

      const originalOpen = window.open ? window.open.bind(window) : null;
      window.open = (url, target, features) => {
        if (typeof url === "string" && /^(https?:|mailto:)/i.test(url)) {
          try {
            postMessage("externalOpen", { url });
            return null;
          } catch (error) {
            console.error("External open bridge failed", error);
          }
        }
        return originalOpen ? originalOpen(url, target, features) : null;
      };

      if (!window.__einsteinMenuBus) {
        const listeners = new Set();
        window.__einsteinMenuBus = {
          on(fn) {
            listeners.add(fn);
            return () => listeners.delete(fn);
          },
          dispatch(command) {
            for (const fn of listeners) {
              try {
                fn(command);
              } catch (error) {
                console.error("Menu listener failed", error);
              }
            }
          }
        };
      }

      if (!window.__dispatchNativeMenu) {
        window.__dispatchNativeMenu = (command) => {
          window.__einsteinMenuBus?.dispatch(command);
        };
      }

      if (!window.nativeTelemetry) {
        window.nativeTelemetry = {
          emit(event, payload = {}) {
            try {
              postMessage("nativeTelemetry", { event, payload });
            } catch (error) {
              console.error("Native telemetry bridge failed", error);
            }
          }
        };
      }

      // Calendar write bridge — adds events to the user's default
      // EventKit calendar. Promise-style like window.storage. Requires
      // EventKit full-access permission (same prompt the read-side
      // bridge already triggered on launch).
      const calendarCallbacks = new Map();
      let calendarNextId = 1;
      const CALENDAR_TIMEOUT_MS = 5000;

      const clearCalendarCallback = (id) => {
        const entry = calendarCallbacks.get(id);
        if (!entry) return null;
        if (entry.timer !== undefined) clearTimeout(entry.timer);
        calendarCallbacks.delete(id);
        return entry;
      };

      window.__nativeCalendarResolve = (id, payload) => {
        const entry = clearCalendarCallback(id);
        if (!entry) return;
        entry.resolve(payload);
      };
      window.__nativeCalendarReject = (id, error) => {
        const entry = clearCalendarCallback(id);
        if (!entry) return;
        entry.reject(new Error(error?.message || "Calendar bridge error"));
      };

      if (!window.nativeCalendar) {
        window.nativeCalendar = {
          /** Insert an event into the user's default writable calendar.
           *  Returns a Promise<{ uid: string }> that resolves once the
           *  event is saved. Rejects if EventKit access was denied or
           *  no writable calendar is available. */
          insertEvent({ summary, start_at, end_at, location }) {
            return new Promise((resolve, reject) => {
              const id = calendarNextId++;
              const timer = setTimeout(() => {
                if (!calendarCallbacks.has(id)) return;
                calendarCallbacks.delete(id);
                reject(new Error("Calendar bridge timed out after " + CALENDAR_TIMEOUT_MS + "ms"));
              }, CALENDAR_TIMEOUT_MS);
              calendarCallbacks.set(id, { resolve, reject, timer });
              try {
                postMessage("nativeCalendar", {
                  id,
                  action: "insert",
                  summary,
                  start_at,
                  end_at,
                  location: location || null
                });
              } catch (error) {
                clearCalendarCallback(id);
                reject(error);
              }
            });
          }
        };
      }

      // Floating companion bridge — fire-and-forget. The Carrel
      // frontend calls window.nativeCompanion.setState('focused')
      // (and similar) from feature hooks; the call is forwarded by
      // the Coordinator to the floating NSPanel's WKWebView. Unknown
      // states are dropped silently on the Swift side.
      if (!window.nativeCompanion) {
        const COMPANION_STATES = new Set([
          "idle", "focused", "thinking", "citeChecking",
          "encouraging", "stumped", "break", "sleeping", "streak",
        ]);
        window.nativeCompanion = {
          setState(state) {
            if (typeof state !== "string" || !COMPANION_STATES.has(state)) return;
            try {
              postMessage("nativeCompanion", { action: "setState", state });
            } catch (error) {
              console.error("Companion bridge setState failed", error);
            }
          },
          setStreakDays(days) {
            const n = Math.max(0, Math.floor(Number(days)));
            if (!Number.isFinite(n)) return;
            try {
              postMessage("nativeCompanion", { action: "setStreakDays", days: n });
            } catch (error) {
              console.error("Companion bridge setStreakDays failed", error);
            }
          },
          setAlarm(active) {
            try {
              postMessage("nativeCompanion", { action: "setAlarm", active: !!active });
            } catch (error) {
              console.error("Companion bridge setAlarm failed", error);
            }
          },
        };
      }

      window.addEventListener("error", (event) => {
        window.nativeTelemetry?.emit("window-error", {
          message: event.message,
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno
        });
      });

      window.addEventListener("unhandledrejection", (event) => {
        const reason = event.reason;
        window.nativeTelemetry?.emit("unhandled-rejection", {
          message: typeof reason === "object" && reason && "message" in reason
            ? reason.message
            : String(reason)
        });
      });

      window.setTimeout(() => {
        if (!window.__einsteinMainStarted) {
          window.nativeTelemetry?.emit("main-script-timeout", {
            href: window.location.href
          });
        }
      }, 1500);
    })();
    """#
}
