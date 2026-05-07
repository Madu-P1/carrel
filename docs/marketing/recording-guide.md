# Recording guide — landing-page assets

> Two videos and one screenshot. Total time: 15-20 minutes. No external tools needed beyond what macOS ships with, plus optionally `ffmpeg` (one Homebrew install).

---

## One-time setup (5 minutes)

Do this once before recording anything. It eliminates the cursor jitter, dock distraction, and unsuitable window framing that ruin most product videos.

### 1. Install ffmpeg (skips if you already have it)

```bash
brew install ffmpeg
ffmpeg -version | head -1
```

If you don't want to install ffmpeg, the recordings still work — you'll just export from QuickTime instead. ffmpeg gets you ~3x smaller files at the same visual quality, which matters for the hero MP4's perf budget.

### 2. Pick the right monitor

Use whichever display has the highest pixel density (your laptop's built-in retina is usually the right one). Avoid recording on a 4K external if you'll deliver at 1080p — you'll waste bits on mip-mapping artifacts.

### 3. Make the desktop quiet

```bash
# Auto-hide the dock so it doesn't appear at the bottom of frames
defaults write com.apple.dock autohide -bool true && killall Dock

# Auto-hide the menu bar
defaults write NSGlobalDomain _HIHideMenuBar -bool true && killall Finder
```

You can revert later with `defaults write ... -bool false` and the same `killall`.

### 4. Plain wallpaper

System Settings → Wallpaper → pick a solid black or near-black image (the default "Macintosh" wallpaper on Sequoia / Tahoe works). A patterned wallpaper bleeds into the cube footage in Recording 3.

### 5. Close everything except Carrel

`Cmd+Q` your way through every other app. The recordings should look like Carrel is the only thing on the machine. Notifications: Focus → Do Not Disturb ON for the next hour.

### 6. Verify the app is running and seeded

```bash
cd /Users/madu/Desktop/Codex && bash script/demo-readiness.sh
```

Should report 8/8 green. If not, fix the red gates first — the recordings depend on this.

---

## Recording 1 — Citation flight (the hero MP4)

**Target:** ~7 seconds, loops cleanly, ≤ 800 KB at 1080p.

### What you're filming

A single user gesture in three beats:
1. Frame opens on the Ask view with a question already answered (citations visible)
2. Cursor moves to a citation chip and clicks
3. The chip flies to the source span in the Reader, the chunk pulses once

### Step 1 — Stage the answer (90 seconds)

1. Open Carrel (`open /Users/madu/Desktop/Codex/dist/EinsteinDesktop.app`).
2. Click **Ask Library** in the sidebar (`⌘5`).
3. In the question input, type a question that's known to produce a clean answer with at least one good citation. Suggested:

   > *What does the lecture say about retrieval practice?*

   Or pick any question you've validated against a real doc in your library. The answer should have at least one cite-able claim — that's what we're going to click.
4. Hit **Ask**. Wait for the answer to fully render. The citations chips appear inline.
5. **Don't click anything yet.** Position the cursor about 100 pixels above the citation chip so it's out of frame for the opening still.

### Step 2 — Set up the recorder (60 seconds)

1. Press `Cmd+Shift+5` to bring up the macOS screen-recorder toolbar.
2. Click **Record Selected Portion** (the right-most icon with a dotted rectangle).
3. Drag a 16:9-ratio box around the part of the Carrel window that contains:
   - The question
   - The answer text
   - At least one citation chip
   - Enough room above the chip for a smooth cursor descent

   A good size is roughly **1280×720** drawn around the right two-thirds of the Carrel window. Don't include the sidebar.
4. Click **Options** in the toolbar:
   - **Microphone:** None
   - **Show Mouse Clicks:** ✓ ON  (the click is the wow moment — we want the visible click ring)
   - **Show Floating Thumbnail:** OFF
   - **Save to:** Desktop
5. Click **Record**.

### Step 3 — Perform the gesture (10 seconds, one take)

1. Wait 1 second after the red-dot recording indicator appears.
2. Move the cursor smoothly to the citation chip. **Don't dart.** A 1-second descent reads cinematic; a 200ms dart reads clipped.
3. Click the citation chip exactly once.
4. Watch the flight. Don't move the cursor during it.
5. After the chunk pulses on landing, hold for one more second (lets the eye absorb the pulse).
6. Press `Cmd+Ctrl+Esc` to stop the recording. (Or click the Stop icon in the menu bar.)

### Step 4 — Trim to ~7 seconds (60 seconds)

1. The recording saved as `Screen Recording YYYY-MM-DD at HH.MM.SS.mov` on your Desktop.
2. Double-click to open in QuickTime Player.
3. `Edit → Trim` (or `Cmd+T`).
4. Drag the yellow handles so the clip is exactly:
   - **In:** 100ms before the cursor enters frame moving toward the chip
   - **Out:** 500ms after the chunk pulse settles
5. Click **Trim**. The clip should be 6-8 seconds.
6. `File → Save` to keep the trimmed `.mov`.

### Step 5 — Export to web-ready MP4 (60 seconds)

**With ffmpeg (preferred):**

```bash
cd ~/Desktop
ffmpeg -i "Screen Recording*.mov" \
  -vf "scale=1920:-2" \
  -c:v libx264 -crf 22 -preset slow -tune film \
  -c:a copy -movflags +faststart \
  citation-flight.mp4
ls -lh citation-flight.mp4
```

This produces an H.264 MP4 at 1080p, ~600-800 KB for a 7-second clip. The `-movflags +faststart` matters: it puts the metadata header at the front of the file so the browser can begin playback before the whole file downloads.

If the file is bigger than 800 KB, bump `-crf 22` to `-crf 26` (more compression, slightly softer image — usually invisible in motion).

**Without ffmpeg (fallback):**

1. In QuickTime: `File → Export As → 1080p`.
2. Save as `citation-flight.mp4` (QuickTime emits H.264 inside `.mov`; rename works for most browsers, but expect the file to be ~3x larger).

### Step 6 — Drop into the repo

```bash
mkdir -p /Users/madu/Desktop/Codex/docs/pitch
mv ~/Desktop/citation-flight.mp4 /Users/madu/Desktop/Codex/docs/pitch/
ls -lh /Users/madu/Desktop/Codex/docs/pitch/citation-flight.mp4
```

That's the file the landing-page hero references. Same file is reused on slide 5 of the investor deck if you want to swap it in.

---

## Recording 2 — Companion states (the cube section)

**Target:** ~12 seconds, four states, autoplays silently, ≤ 600 KB at 1080p.

### What you're filming

The floating cube cycling through four states with no mouse, no chrome, no other windows. Just the cube on a black canvas.

### Step 1 — Get the cube in the frame (30 seconds)

1. Open Carrel. The cube auto-spawns in a corner.
2. **Drag the cube** to the center-ish of an empty area of your desktop (you set the wallpaper to plain black in setup, so any clear spot works). The cube uses an `.nonactivatingPanel` so dragging it doesn't steal focus from anywhere.
3. Hide the main Carrel window: `⌘H`. The cube stays — it's a separate panel with `.canJoinAllSpaces`.

You should now have just the cube visible on a near-black desktop. Nothing else.

### Step 2 — Open the JS console for the main window (60 seconds)

The cube is controlled via JS sent from the Carrel main window's webview. So:

1. `⌘N` (or click the Carrel window in the dock) to bring the main window back.
2. **Right-click anywhere in the main Carrel window** → **Inspect Element**. (The webview has `isInspectable=true`, set in `macos-app/Sources/EinsteinDesktopApp/WebAppView.swift:53`.)
3. Safari Web Inspector opens. Click the **Console** tab.
4. **Don't close the inspector yet.** Move it to a different desktop space (or your second monitor if you have one) so the cube stays visible while the inspector is open.

Smoke test: paste this in the console and press Return.

```js
window.nativeCompanion.setState('focused')
```

The cube should rotate and shift to its `focused` face. If nothing happens, check the inspector's Console for errors and verify the cube is still on screen.

### Step 3 — Set up the recorder (60 seconds)

1. `Cmd+Shift+5` again.
2. **Record Selected Portion**.
3. Drag a tight box around just the cube + ~20px margin on every side. Aim for roughly 240×240. Don't include the inspector or the wallpaper edges — just the cube area.
4. **Options:**
   - **Microphone:** None
   - **Show Mouse Clicks:** OFF  (no mouse in this footage)
   - **Show Floating Thumbnail:** OFF
   - **Save to:** Desktop
5. Click **Record**.

### Step 4 — Run the state sequence (12 seconds, one take)

In the inspector's console, **paste this entire block and press Return**:

```js
(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  // 1. Idle (twinkles, drifts)
  window.nativeCompanion.setState('idle');
  await wait(3000);
  // 2. Thinking (Carrel is reading the source)
  window.nativeCompanion.setState('thinking');
  await wait(3000);
  // 3. Encouraging (you got the card)
  window.nativeCompanion.setState('encouraging');
  await wait(3000);
  // 4. Sleeping (your library is on disk; so am I)
  window.nativeCompanion.setState('sleeping');
  await wait(2500);
})();
```

Then immediately switch to the desktop space where the cube is recording. Don't touch anything for 12 seconds. Each state holds for 3 seconds (sleeping holds 2.5s) so the eye has time to absorb the transition.

When the sequence finishes, press `Cmd+Ctrl+Esc` to stop the recording.

### Step 5 — Trim and export (90 seconds)

Same as Recording 1, with two differences:

- Trim to start exactly when the cube transitions from initial-state to `idle`'s drift, and end exactly when `sleeping`'s glimmer finishes its second cycle. ~12 seconds total.
- Export at a smaller frame size — the cube is at most 200×200, no point delivering 1080p:

```bash
cd ~/Desktop
ffmpeg -i "Screen Recording*.mov" \
  -vf "scale=480:-2" \
  -c:v libx264 -crf 22 -preset slow -tune film \
  -an -movflags +faststart \
  companion-states.mp4
ls -lh companion-states.mp4
```

Target ~300-600 KB at 480p. The `-an` strips audio entirely (it was already off in recording, but the flag makes it explicit).

### Step 6 — Drop into the repo

```bash
mv ~/Desktop/companion-states.mp4 /Users/madu/Desktop/Codex/docs/pitch/
ls -lh /Users/madu/Desktop/Codex/docs/pitch/companion-states.mp4
```

---

## Recording 3 — Companion in context (the wide still)

**Target:** one PNG, 1920×1080 or full retina width, < 200 KB.

### What you're filming

A real desktop with a non-Carrel app frontmost (Notion, VS Code, Spotify — pick whatever the visitor would recognize) and the cube parked unobtrusively in a corner. The story: "the cube is always there, never in the way."

### Steps

1. Open Notion (or your editor of choice). Resize it to fill ~75% of the screen.
2. Drag the cube to the **top-right corner** of your screen, about 24px from each edge. The corner placement reads as "decoration on the room," not "focus of the room."
3. Make sure the menu bar is auto-hidden (from setup) so the cube isn't fighting it for vertical space.
4. `Cmd+Shift+4` → press **Space** → click on the **Notion window** (or whichever app you chose). This captures the active window with shadow, framed cleanly.
5. The PNG saves to Desktop. Crop to include the cube using `Preview.app`:
   - Open the PNG.
   - `Tools → Adjust Size` to confirm dimensions.
   - Crop with `⌘K` so the cube is visible at the top-right edge of the crop region.
6. Optimize the PNG:

```bash
cd ~/Desktop
# Optional but recommended:
brew install pngquant 2>/dev/null
pngquant --quality=70-90 --output companion-context.png "Screenshot*.png"
ls -lh companion-context.png
```

7. Drop it next to the videos:

```bash
mv ~/Desktop/companion-context.png /Users/madu/Desktop/Codex/docs/pitch/
```

---

## Final checklist

After all three are done:

```bash
ls -lh /Users/madu/Desktop/Codex/docs/pitch/
```

You should see:
- `citation-flight.mp4`         (~600-800 KB, 7s)
- `companion-states.mp4`        (~300-600 KB, 12s)
- `companion-context.png`       (< 200 KB, 1 frame)

Total ≤ 1.6 MB. The whole landing-page asset pack fits in one round-trip on a 4G connection.

---

## Common mistakes (from doing this wrong already)

- **Not stopping at exactly 7s.** Investors and students alike bounce after 8s of motion. The hero loop must finish under 8s. If it's 9s, cut a beat.
- **Including the cursor in the cube video.** Recording 2 should have NO mouse pointer. Verify the "Show Mouse Clicks" toggle is OFF before you start.
- **Light wallpaper bleeding into the cube.** The cube's background is `rgba(22,22,26,0.92)` — semi-transparent. On a non-dark wallpaper, the cube reads as muddy. Always pure-black or near-black wallpaper for Recording 2 + 3.
- **Letting the dock or menu bar appear mid-frame.** They auto-show on cursor proximity. During recording, keep the cursor in the middle of the frame, not at screen edges.
- **Exporting at default QuickTime quality.** Files come out ~5-8 MB and the page perf budget can't absorb that. Always re-encode through ffmpeg with `-crf 22`.
- **Recording on battery.** macOS reduces GPU clock on battery; the cube animation can drop to 30 fps. Plug in before recording.
