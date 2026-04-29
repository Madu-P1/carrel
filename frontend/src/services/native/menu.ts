export type MenuCommand =
  | "app.preferences"
  | "file.new"
  | "file.import"
  | "view.toggleLeftSidebar"
  | "view.toggleRightPanel"
  | "view.toggleTheme"
  | "view.zoomIn"
  | "view.zoomOut"
  | "view.zoomReset"
  | "nav.dashboard"
  | "nav.session"
  | "nav.library"
  | "nav.reader"
  | "nav.ask"
  | "nav.study"
  | "nav.plan"
  | "reader.nextPage"
  | "reader.prevPage"
  | "palette.open"
  | "help.shortcuts"
  | "help.open";

type Listener = (cmd: MenuCommand) => void;

interface MenuBus {
  on(fn: Listener): () => void;
  dispatch(cmd: string): void;
}

declare global {
  interface Window {
    __einsteinMenuBus?: MenuBus;
    __dispatchNativeMenu?: (command: string) => void;
  }
}

function createBus(): MenuBus {
  const listeners = new Set<Listener>();

  return {
    on(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    dispatch(command) {
      for (const listener of listeners) {
        try {
          listener(command as MenuCommand);
        } catch (error) {
          console.error("Menu listener failed", error);
        }
      }
    }
  };
}

export function ensureMenuBus(): MenuBus {
  if (!window.__einsteinMenuBus) {
    window.__einsteinMenuBus = createBus();
  }

  if (!window.__dispatchNativeMenu) {
    window.__dispatchNativeMenu = (command: string) => {
      window.__einsteinMenuBus?.dispatch(command);
    };
  }

  return window.__einsteinMenuBus;
}

export function onMenuCommand(fn: Listener): () => void {
  return ensureMenuBus().on(fn);
}

export function dispatchMenuCommand(command: MenuCommand): void {
  ensureMenuBus().dispatch(command);
}
