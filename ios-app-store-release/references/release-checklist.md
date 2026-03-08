# Release Checklist

## Repo signals to inspect first

Look for these before acting:
- `fastlane/Fastfile` for `beta`, `release`, `build`, or screenshot lanes
- `fastlane/Appfile` for bundle identifiers and App Store Connect app config
- `docs/appstore-metadata.md` or `fastlane/metadata/` for release copy
- `Screenshots/` or `fastlane/screenshots/` for current asset naming
- release scripts in `Scripts/` or README instructions
- Xcode schemes and export settings

## Recommended execution order

1. Discover repo-specific release tooling.
2. Decide the release mode.
3. Refresh screenshots.
4. Update version/build numbers.
5. Update release notes and metadata.
6. Run a build-only validation step.
7. Upload to TestFlight or App Store.
8. Report artifacts and follow-up steps.

## Screenshot workflow guidance

- Capture only required devices/locales.
- Use consistent filenames so diffs are easy to review.
- Remove transient overlays, permission prompts, debug banners, and incomplete loading states.
- For watchOS, capture stable workout or summary states, not fleeting countdowns unless intentionally marketing them.
- Verify the output folder contents after capture.

## Metadata workflow guidance

Prefer an existing source-of-truth file such as:
- `docs/appstore-metadata.md`
- `fastlane/metadata/<locale>/` files
- product or marketing docs that explicitly drive the store listing

Update:
- app name / subtitle only when explicitly requested
- What's New / release notes every release
- reviewer notes when new permissions, pairing flows, or hardware requirements changed
- support / privacy URLs only if the destination changed

## Upload workflow guidance

Prefer repo-native commands in this order:
1. repo fastlane lane
2. documented Xcode archive/export/upload flow
3. only then ad-hoc commands

Typical fastlane modes:
- TestFlight: `fastlane ios beta`
- App Store binary upload: `fastlane ios release`
- Build-only: `fastlane ios build`

Use `bundle exec` if the repo is Bundler-managed. Otherwise use direct `fastlane`.

Before upload, verify:
- App Store Connect API key path or login method
- signing/provisioning readiness
- correct scheme
- correct platform target
- version/build updated

## Example repo signals: RunnersHeart

If working inside `RunnersHeart`, current signals include:
- `fastlane/Fastfile`
  - `ios beta`: build and upload to TestFlight
  - `ios release`: build and upload to App Store with metadata/screenshots skipped
  - `ios build`: build only
- `docs/appstore-metadata.md`
  - English and Korean App Store copy
  - What's New section
  - reviewer notes and support/privacy URLs
- `Screenshots/`
  - current store or marketing screenshots

In this repo, the likely safe sequence is:
1. refresh screenshots if needed
2. update `docs/appstore-metadata.md`
3. run a build validation
4. run `fastlane ios beta` or `fastlane ios release` depending on target

## Output template

When the release task ends, report:
- release mode executed
- screenshots refreshed and output paths
- metadata files changed
- version/build values
- upload/build command run
- result URL or artifact path when available
- remaining manual next steps
