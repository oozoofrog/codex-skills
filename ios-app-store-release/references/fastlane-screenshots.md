# Fastlane Screenshot Automation

## Purpose

Use this reference when a repo needs repeatable App Store screenshot generation and already uses fastlane or would clearly benefit from adding a minimal fastlane screenshot lane.

## When to add a screenshot lane

Add screenshot automation when:
- screenshots are part of repeated release work
- the repo already uses fastlane for build/upload
- manual simulator capture is too fragile or time-consuming
- the app has stable UI test or preview-driven routes into the required screens

Do **not** add a screenshot lane just for a one-off urgent upload if manual capture is faster and reliable enough.

## Preferred minimal shape

### Fastfile lane

Prefer a simple lane such as:

```ruby
lane :screenshots do
  capture_screenshots(
    scheme: "AppScreenshots",
    output_directory: "Screenshots",
    clear_previous_screenshots: false
  )
end
```

Use `capture_screenshots` / `snapshot` rather than custom shell orchestration when the repo is already on fastlane.

## Supporting files

Add only what is needed:
- `Snapfile` when central device/language config helps
- `SnapshotHelper.swift` in the UI test target when using fastlane snapshot conventions
- minimal UI test flows to drive stable capture states

## Design rules

- Reuse the repo's existing screenshot folder when possible.
- Keep filenames and device coverage consistent across releases.
- Prefer stable fake/demo/sample data paths.
- Remove permission prompts, loading spinners, transient timers, and debug overlays before capture.
- Avoid rewriting release/upload lanes while adding screenshot automation.

## Device and locale strategy

Start with the minimum store set the repo already appears to use.
If the repo already has files like `iPhone_01_...` and `Watch_01_...`, preserve that taxonomy.
Only expand device/language coverage when the user explicitly asks.

## RunnersHeart-specific hint

For RunnersHeart, a good first iteration is:
- keep output in `Screenshots/`
- preserve filenames like `iPhone_01_WorkoutList.png` and `Watch_01_Main.png`
- add a dedicated screenshot/UI-test route instead of trying to manually navigate from cold launch every release
- keep watch captures to stable, non-transient screens

## Report requirements

When you add or update screenshot automation, report:
- which lane was added or changed
- which supporting files were added
- output directory
- devices/locales covered
- whether capture was actually run successfully
