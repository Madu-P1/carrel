enum NativeBridge {
    static let storageHandlerName = "nativeStorage"
    static let externalOpenHandlerName = "externalOpen"
    static let menuHandlerName = "nativeMenu"
    static let telemetryHandlerName = "nativeTelemetry"

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
