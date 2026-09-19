# Local runtime fixes — 2026-09-20

The launcher and Python runtime are separate installations. `runtime-fixes.patch` is the
cumulative delta against the existing local Codex/Luna adapter, not an upstream installer.
Preserve the existing adapter and credentials. From the runtime, check with
`git apply --check /absolute/path/runtime-fixes.patch` before applying elsewhere;
an already patched installation can use `git apply --reverse --check`. Do not overwrite
local changes or apply a patch twice to make it fit.

## Execution paths

- Named app: resolve PID and observed window ID, capture that individual window (including
  when covered), translate capture coordinates, and pin the window for the run.
- Accessibility: inspect the selected window/sheet before a browser's page tree; do not
  prune nested anonymous containers solely because they share a frame. AXPress/AXValue
  target the control and preserve foreground focus.
- Native input without usable AX: temporarily activate the requested app, validate the
  window and click hit-test, then restore the previous app. Do not undo a newer user focus
  choice. `--background-only` refuses this fallback. Process-directed mouse dispatch was
  observed to miss its target and is not used as a successful fallback.
- Missing, moved or changed windows and changed control pixels are refused before input.
  A focused field outside the selected window is not offered to the writer.
- Locked GUI sessions stop input. Window targeting does not bypass lock-screen credentials.

Unscoped screen tasks retain the older main-display path. Korean/English OCR is the local
default; Retina images are normalized to 1920 pixels and coordinates restored afterward.
`CLICKER_FULL_SCREEN=0` restores cropped OCR in unscoped mode. Targeted OCR does not filter
out genuine controls just because their label appears in the goal.

Answers retain `answer-raw.png` and `answer-evidence.json` with target PID/window identity
and actual foreground app. `goal_achieved` remains a model claim and requires verification.
Window disappearance after a dialog click is not by itself a successful task result.

## Verification

- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`: 169 tests passed.
  Coverage includes target/window coordinates, stale controls, missing targets, nested AX
  groups, lock-state refusal, focused fields from another window, and focus restoration.
- Saved-dialog replay `20260920-002836`: Jev chose the Allow item (0.99); no live click.
- Live `20260920-005054`: actual foreground was ChatGPT, target was Chrome window 1449.
  Jev selected the observed Allow button, AXPress dismissed it, and an independent
  Ultrafast status check returned `healthy: true`, `browser_ready: true`.
- Isolated AppKit fixture: background AX text entry and button click saved the expected
  text/count while ChatGPT remained foreground. A forced OCR-only click subsequently
  used temporary target focus and returned to ChatGPT. Private machine evidence:
  `runs/background-fixture/verification.json` and `scoped-focus-verification.json`.
  The repeatable fixture source is `tests/jev/fixtures/background_native.swift` in the
  skill repository; compile with swiftc and supply an existing output directory.
- Source and installed skill copies are compared; runtime patch reverse checks are used
  separately. A fresh Codex session's skill discovery is not part of these checks.

These cases do not establish parity or superiority over every Codex computer-use capability.
Canvas-only controls, minimized/unrendered windows, and apps that reject accessibility or
activation need case-specific testing. The controller lock protects these two launchers,
not unrelated tools or direct runtime commands.
