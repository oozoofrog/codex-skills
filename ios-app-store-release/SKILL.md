---
name: ios-app-store-release
description: End-to-end App Store and TestFlight release preparation for iOS and watchOS apps. Use when Codex needs to refresh or automate App Store screenshots, add or update fastlane screenshot lanes, update version/build numbers, write What's New or release notes, sync metadata source files, validate release readiness, and build or upload binaries with fastlane, Xcode, or the repo's existing App Store delivery workflow.
---

# iOS App Store Release

## Overview

Prepare an iOS or watchOS app for TestFlight or App Store release by reusing the repository's existing release tooling. Prefer the repo's current fastlane lanes, metadata files, screenshot directories, and Xcode schemes over inventing a new pipeline.

## Quick start

1. Discover repo release signals before changing anything.
2. Run a preflight check for missing inputs: version/build target, release notes, screenshots, signing, and App Store Connect credentials.
3. Lock the release target: screenshots only, metadata only, build only, TestFlight upload, or App Store binary upload.
4. Refresh screenshots in the repo's existing output location.
5. Update version/build numbers and release copy in the source-of-truth files.
6. Run at least one concrete validation step before upload.
7. Upload with the repo's existing lane or build command.
8. Report changed files, captured screenshots, version/build, upload result, missing prerequisites, and remaining manual steps.

For a detailed checklist and repo-signal patterns, read `references/release-checklist.md`.

## Workflow

### 1. Discover repo release signals

Search for these first:
- `fastlane/Fastfile`, `fastlane/Appfile`, `fastlane/metadata/`
- `docs/appstore-metadata.md` or similar source-of-truth release copy
- `Screenshots/`, `fastlane/screenshots/`, marketing asset folders
- screenshot automation signals such as `SnapshotHelper.swift`, UI test targets, `Snapfile`, or screenshot lanes in `Fastfile`
- Xcode project/workspace, schemes, export or upload scripts
- existing release docs in `README`, `docs/`, or repo-specific instructions

Prefer the existing workflow. Do not introduce fastlane if the repo already ships with pure Xcode tooling, and do not replace a working fastlane lane with ad-hoc shell commands unless the lane is broken.

### 2. Resolve missing inputs before locking the target

Before upload or screenshot work, probe for these inputs and either derive them, guide the user, or perform the missing setup if safe:
- release version and build number
- What's New / release notes source text
- screenshot source states and output directory
- App Store Connect credentials or API key path
- signing / provisioning readiness
- locale-specific metadata gaps

Rules:
- Derive values from repo source-of-truth files when possible.
- Draft missing release notes from recent commits, PR titles, or changed user-facing features.
- Reuse or refresh screenshots when the output path already exists.
- Search common local paths and env vars for App Store Connect credentials before declaring them missing.
- If a required credential or asset is truly missing, stop the irreversible step and report the exact missing file, expected path, and the next action needed from the user.
- If the user provides the missing file path and the repo expects a fixed location, copy or wire it in with the smallest safe change instead of asking the user to redo the whole process manually.
- For App Store Connect API keys, explain where the user can create or download the key in App Store Connect, which access role is typically needed, that the `.p8` private key is only downloadable once, and where the file should be placed locally before retrying.

### 3. Lock the release target

Classify the request into one of these modes:
- screenshot refresh
- metadata / release notes update
- build only
- TestFlight upload
- App Store binary upload
- full release prep

Before running external side effects such as TestFlight upload, App Store upload, or review submission, restate the exact action, lane, target scheme, and whether all required inputs were found or derived.

### 4. Refresh screenshots

Capture screenshots only after the app is in a stable visual state.
- Reuse the repo's existing screenshot directory and filename convention.
- Prefer deterministic simulator/device targets already used by the repo.
- For watchOS, capture non-transient states and avoid permission prompts or onboarding noise.
- Replace stale assets deliberately instead of spraying new filenames.
- If both iPhone and Apple Watch screenshots matter, keep the set complete rather than mixing fresh and stale subsets.

Use the available simulator/build tools first. If a repo already has screenshot automation, prefer it over manual capture. If the repo uses fastlane for release work but lacks screenshot automation, you may add a minimal screenshot lane and the required snapshot setup rather than inventing a separate pipeline.

### 5. Add or update screenshot automation when missing

If the repo uses fastlane but does not have a screenshot lane, you may add one.

Preferred order:
- reuse an existing screenshot lane if present
- add a minimal `screenshots` or `capture_screenshots` lane in `fastlane/Fastfile`
- add or update `Snapfile` only if the repo benefits from central device/language configuration
- add the smallest UI test coverage needed to drive stable capture states

Rules:
- keep lane names obvious, such as `screenshots`
- reuse the repo's existing screenshot output folder if one already exists
- avoid refactoring unrelated fastlane lanes
- prefer deterministic UI test routes over manual simulator choreography when the screenshots will be reused every release
- for watchOS, define stable paired-device or preview states before automating capture

Read `references/fastlane-screenshots.md` before adding screenshot automation.

### 6. Update versioning and release copy

Find the source of truth for:
- marketing version
- build number
- What's New / release notes
- App Store description, subtitle, keywords, reviewer notes

Rules:
- describe shipped user-facing changes, not internal refactors
- separate internal diagnostics from user value
- avoid overstating hidden fixes or speculative benefits
- keep multi-language metadata in sync when the repo stores more than one locale
- update the repo source file first; only then mirror into upload tooling if needed

### 7. Validate release readiness

Run at least one meaningful validation step before upload:
- build the release target
- run the repo's build-only lane
- verify screenshot outputs exist in the expected folder
- verify version/build and metadata changes landed in the right files

If signing or credentials are uncertain, prefer a build-only pass before upload.

### 8. Upload the binary

Prefer the repo's existing delivery path:
- `bundle exec fastlane ...` when the repo is Bundler-managed
- otherwise `fastlane ...`
- otherwise the repo's documented Xcode or shell upload flow

Keep build-only, TestFlight upload, and App Store upload separate in your reasoning. Reuse existing lanes when they already encode signing, export method, or App Store Connect credentials.

Do not submit for App Review or release to production unless the user explicitly asks for that final step.

### 9. Report completion cleanly

Always report:
- release mode you executed
- files changed
- screenshot outputs refreshed
- version/build values
- release notes / What's New text
- build or upload command actually run
- remaining manual next steps, if any

## Release copy rules

- Write in user language, not engineering language.
- Prefer short bullets for What's New.
- Mention fixes only if the user will notice the benefit.
- Do not surface internal-only warnings, refactors, or implementation details unless they changed user experience.
- If the repo keeps English and Korean copy, update both together or explicitly mark one locale pending.

## Decision guardrails

- Prefer the repo's existing lane names, metadata files, and screenshot folders.
- Prefer minimum viable changes over release-process refactors.
- Keep irreversible actions explicit.
- When upload tooling fails, summarize the exact blocking credential, signing, or App Store Connect issue instead of masking it.

## Missing-input resolver

When something needed for release is missing, prefer this order:

1. **Search locally first**
   - common credential paths such as `~/.appstoreconnect/`, env vars, repo-local secrets paths, and documented config files
   - existing screenshot directories and metadata files
2. **Derive what can be derived**
   - next build number from project settings
   - release notes from recent user-facing commits and metadata history
   - screenshot targets from existing filenames and folders
3. **Do the setup if the missing data is available**
   - if the key file exists in another safe local path, copy it to the expected path
   - if release notes are missing, draft them and update the source-of-truth file
   - if screenshots are stale but the app can be built, capture replacements into the existing directory
   - if screenshot capture will be repeated, prefer adding or updating a fastlane screenshot lane instead of relying on one-off manual steps
4. **Escalate only the truly missing prerequisite**
   - tell the user the exact file/value still needed
   - include expected path, why it is needed, and the next command or step Codex will run once it exists

Never fabricate credentials, reviewer data, or store assets. Only automate setup when the necessary data already exists or the user explicitly provides it.

## References

- Read `references/release-checklist.md` when you need the detailed step-by-step checklist, repo-signal examples, or output template.
- Read `references/missing-inputs.md` when credentials, screenshots, version info, or metadata sources are missing and you need the exact recovery pattern.
- Read `references/app-store-connect-api-key.md` when App Store Connect API key setup is missing and you need exact user guidance or local file wiring steps.
- Read `references/fastlane-screenshots.md` when a repo lacks screenshot automation and you need to add or update a fastlane screenshot lane.
