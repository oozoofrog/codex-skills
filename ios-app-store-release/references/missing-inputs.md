# Missing Inputs and Credential Recovery

## Purpose

Use this guide when release work is blocked by missing version info, screenshots, metadata copy, credentials, or signing prerequisites.

## Recovery patterns

### 1. Version/build not provided

Prefer this order:
1. read `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` from the Xcode project
2. inspect previous release notes or tags
3. propose the next patch version and build increment
4. apply only after the release target is confirmed

### 2. Release notes missing

Draft from:
- recent commits since the last release prep commit
- merged PR titles
- user-facing changes in docs or product specs

Rules:
- keep bullets user-facing
- avoid internal-only diagnostics
- update all maintained locales together when possible

### 3. Screenshots missing or stale

Check for:
- `Screenshots/`
- `fastlane/screenshots/`
- existing naming patterns like `iPhone_01_...`, `Watch_01_...`

If capture tooling already exists, use it. Otherwise:
- build the app first
- boot the expected simulator/device
- navigate to stable visual states
- overwrite the existing filenames deliberately

If screenshots are not required for the immediate task, say so and continue with metadata/build/upload.

### 4. App Store Connect API key or login missing

Check in this order:
1. path hardcoded in `fastlane/Fastfile`
2. `~/.appstoreconnect/`
3. repo-local documented secret paths
4. environment variables used by the repo

If the expected key file is missing:
- report the exact missing path
- explain which lane or command depends on it
- if the file exists elsewhere locally, copy it into place
- if the user provides a new path, either copy it to the expected location or patch config with minimal change

Never invent credentials or create placeholder key files.

### 5. Signing/provisioning uncertain

Do a build-only validation first.

If the repo's upload lane also builds, run the build lane separately before upload so failures are easier to classify into:
- signing/provisioning
- App Store Connect auth
- code/build issue

## Reporting blocked state

When blocked, report using this structure:
- missing item
- expected path or source
- why it is needed
- what Codex already checked
- what Codex can do automatically once it is available

## Example: RunnersHeart

If `fastlane ios beta` fails because `~/.appstoreconnect/AuthKey_7PH7U56LNM.p8` is missing:
- keep version/build and metadata updates in place
- keep build validation results
- tell the user the exact path that fastlane expects
- offer to resume upload immediately once the key file is placed there or another local key path is provided
