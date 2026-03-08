# App Store Connect API Key Recovery

## When to use this reference

Use this when release work is blocked because `fastlane` or another upload tool expects an App Store Connect API key `.p8` file and the file is missing locally.

## What the user needs to know

An App Store Connect API key is created in **App Store Connect**, not in Xcode and not in Apple Developer Certificates/Profiles.

Typical navigation path:
1. Sign in to **App Store Connect**
2. Open **Users and Access**
3. Open the **Integrations** tab
4. Open **App Store Connect API**
5. Create a new API key if one does not already exist
6. Download the `.p8` private key file

Direct signed-in page for API keys:
- `https://appstoreconnect.apple.com/access/integrations/api`

If the user is already signed in and has the right permissions, this direct URL is usually the fastest path and should be given before generic help documentation.

Important:
- The `.p8` private key can usually be downloaded **only once** at creation time.
- If the original `.p8` file was lost, the user normally needs to create a **new key** and use that new file.
- The repo may also require the matching **Key ID** and **Issuer ID** already configured in `Fastfile` or CI secrets.
- Some accounts first show **Request Access** on the API page. If that appears, the Account Holder may need to request or enable App Store Connect API access before a key can be generated.

## What to tell the user

When the key is missing, do not just say “file not found.” Explain:
- the exact missing filename
- the exact local path expected by the repo
- the direct App Store Connect URL where they can create the key: `https://appstoreconnect.apple.com/access/integrations/api`
- that the `.p8` file is one-time-download
- that if they already have the file elsewhere on disk, Codex can copy it into place automatically

## Typical local setup flow

If the repo expects a fixed path such as:
- `~/.appstoreconnect/AuthKey_ABC123XYZ.p8`

then guide or perform this flow:
1. Check whether the file already exists in another local folder
2. If it exists, create `~/.appstoreconnect/` if needed
3. Copy the file to the expected path
4. Re-run the blocked upload command

Example shell pattern:
```bash
mkdir -p ~/.appstoreconnect
cp /path/from/user/AuthKey_ABC123XYZ.p8 ~/.appstoreconnect/AuthKey_ABC123XYZ.p8
```

## If the Fastfile hardcodes key metadata

A typical fastlane config includes:
- `key_id`
- `issuer_id`
- `key_filepath`

If only `key_filepath` is missing and the `key_id` / `issuer_id` are already present, the smallest safe fix is usually to place the correct `.p8` file at the expected path.

If the user creates a brand-new key and the repo hardcodes the old `key_id`, then you may need to update fastlane config as well. In that case:
- ask for the new **Key ID** and confirm the **Issuer ID**
- patch the config minimally
- report exactly what changed

## Role / permission guidance

If the user asks what access they need, tell them:
- they need App Store Connect access that allows API key management or access to an existing API key provisioned by their team
- exact org policy varies, but this is usually managed by the account owner/admin team
- if they cannot see **Users and Access → Integrations → App Store Connect API**, they likely need a teammate with sufficient permissions

## RunnersHeart-specific example

If `fastlane/Fastfile` expects:
- `~/.appstoreconnect/AuthKey_7PH7U56LNM.p8`

then tell the user:
- the upload is currently blocked only because this file is missing locally
- if they already have `AuthKey_7PH7U56LNM.p8` somewhere else, provide the path and Codex can copy it into `~/.appstoreconnect/`
- if they no longer have the file, they likely need to create a new App Store Connect API key in App Store Connect and either:
  - provide the new `.p8` path and update the repo config if the key id changed, or
  - replace the local file if the existing config still matches

## Output pattern when blocked

Use a message shaped like this:
- Missing item: `~/.appstoreconnect/AuthKey_XXXX.p8`
- Why needed: required by `fastlane ios beta` / `app_store_connect_api_key`
- Direct page: `https://appstoreconnect.apple.com/access/integrations/api`
- Fallback navigation: App Store Connect → Users and Access → Integrations → App Store Connect API
- Important note: `.p8` downloads once; if lost, create a new key
- What Codex can do next: copy the file into place and immediately rerun the upload command
