import { render } from "preact";

import { CachetApp } from "./CachetApp";
// Brings the global tokens (incl. the self-hosted fonts), the reset, the theme
// vars, and the keyframe library the verify seal rides on. Same base as Carrel.
import "../main.css";

// The Instrument is paper, always: no dark mode. Force the light register so the
// shared design-system primitives (Button, Toast) sit correctly on paper. The
// verify and shelf surfaces scope their own paper palette regardless.
const docEl = document.documentElement;
docEl.classList.remove("theme-dark");
docEl.classList.add("theme-light");

const root = document.getElementById("root");
if (!root) {
  throw new Error("Missing #root container");
}

render(<CachetApp />, root);
