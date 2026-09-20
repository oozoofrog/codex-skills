# Background browser validation — 2026-09-20

The existing local runtime is `/Users/oozoofrog/.local/share/jev-ultrafast`. The
[runtime patch](runtime-fixes.patch) preserves its Codex Luna text adapter and changes
only browser initialization/cleanup plus their offline tests. Check with
`git apply --check` before applying to another compatible checkout; use
`git apply --reverse --check` to verify an already patched runtime.

A new owned tab is created with `background=True`. Focus emulation is enabled before
changing viewport metrics so a hidden renderer is awake for its repaint. A constructor
failure closes only the tab it created. No browser restart or profile replacement is used.
The runner stores private initial/step/final observations and failure context. An input
error can be ambiguous; it is not automatically replayed and a fresh observation is
attempted separately. A model's DONE status is still not independent proof.

## Evidence

- `uv run ruff check .`, `uv run pytest -q`: 35 offline tests passed. Browser initialization
  order and owned-tab cleanup are covered; model calls are stubbed.
- `node --check jev_ultrafast/static/app.js`, `uv build`: passed.
- `uv run python scripts/check_guards.py`: 21 real Chrome checks passed, including native
  dropdown selection, real text input and asynchronous suggestions, stale document/control
  rejection, and occlusion checks. The fixture uses a local data URL and makes no model calls.
- An earlier account-menu attempt hit an Input.dispatchMouseEvent timeout; it is not counted
  as success. A subsequent local guard run also exposed initialization timeout. The retained
  failure context and initialization changes address these failure paths without replaying
  an uncertain mutation.
- Actual account lookup completed in the background at `/settings/billing`. Run
  `runs/20260919-155857-686346` contains the final screenshot and fresh DOM observation.
  Both show the same remaining credit amount and expiry. ChatGPT remained foreground.
  Account values and screenshots are private runtime evidence, not repository content.
- The goal explicitly allowed reading Settings while forbidding saving changes; a less
  precise goal had stopped at the account menu. Read-only navigation should be distinguished
  from changing settings when composing task goals.

The repository launcher regression suite has 7 passing tests, including ambiguous timeout
recording without replay. Local-link checks and both skill validators are separate checks.
At the time of this validation, the optional distribution suite had a separate
marketplace inventory mismatch. This run did not change the marketplace; the later
[Jev test report](../../docs/jev/TEST_REPORT.md) records its resolution.

This validates the specified workflow, not universal equivalence to Codex computer use.
Frames, shadow roots, file uploads, popup tabs and canvas widgets remain outside this
browser agent's existing MVP. Native dialogs use the targeted Computer Use path instead.
