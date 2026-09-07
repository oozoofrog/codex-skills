# Compatibility and version maintenance

The structured baseline is [compatibility.json](compatibility.json), with tested scenarios and limits in [runtime validation](runtime-validation.md). Sources, dates, and local input hashes are in [sources](sources.md). Skill package version, desktop app version, web editor feature availability, and CUA API compatibility are separate facts. Matching a desktop version does not prove current web features are unchanged.

## During normal use

At first Figma use in a session, read the small baseline and reuse any fresh checks already in the task. For a native app, inspect About through computer-use or read the installed bundle's metadata with a filesystem tool. Reading metadata is not shell UI automation. On macOS, after confirming the app location:

```bash
plutil -extract CFBundleShortVersionString raw /Applications/Figma.app/Contents/Info.plist
plutil -extract CFBundleVersion raw /Applications/Figma.app/Contents/Info.plist
```

For browser-only work, record desktop version as not applicable. If the source review predates today's session, check the official product release notes once for relevant changes even when the desktop version matches. Reuse that result for the session. Do not re-fetch all articles if nothing relevant changed.

If the app version, tool signatures, or relevant UI differs, consult the affected official manual and observe the current UI before using the old procedure. Compare meaning, not just a moved button. Record the mismatch and the supported replacement in the task. If the web source is unavailable, continue only operations whose current UI provides sufficient evidence; state that the manual refresh could not be confirmed. Unknown version does not automatically forbid a visible, unambiguous UI action.

Normal design work can adapt to observed UI without modifying installed skill files. A persistent skill refresh follows the workflow below when requested. Do not mutate a plugin cache, install software, restart the user's app, or create a scheduled monitor merely because a version changed.

## Refresh the manuals and version

Trigger examples: `$figma-computer-use 매뉴얼을 최신 Figma에 맞춰 갱신하고 버전업해주세요`, or a request to fix a demonstrated compatibility failure in this skill.

1. Locate the maintained source checkout and applicable instructions; inspect Git state and preserve unrelated changes. Read skill-creator for material skill edits. If working on plugin distribution, use plugin-creator as applicable. Installed cache paths are not the editable source of truth. If only a cache exists, prepare the proposed edits and resolve the intended source location before publishing changes there.
2. Read S10 and relevant official manuals newer than or changed since the recorded review. Use stable article IDs where possible. Verify redirects and replacement topics; do not replace broken links with guessed URLs. Compare local sources only if relevant, retaining provenance/hashes. Never import MCP instructions as computer-use operations.
3. Update the affected internal procedure and source-register assessment. Separate removed/renamed controls, added capabilities, access/plan changes, and runtime API changes. Keep unrelated Figma product releases out of a Figma Design workflow. Record inaccessible sources and documentation-only claims explicitly.
4. Verify the changed procedure against available read-only UI. For editing/prototype/export behavior, use a specifically authorized test file/workflow; a maintenance request alone is not permission to create or modify a design. Record unexecuted scenarios rather than claiming compatibility. If a change cannot be verified sufficiently for use, mark that operation unresolved while retaining verified operations.
5. Update `compatibility.json` review/app/runtime/product evidence to what was actually checked. Bump the skill and plugin together: patch for corrective guidance, minor for added operations, major for incompatible invocation/runtime requirements. A date-only recheck with no content or baseline change needs no version bump. Never copy the Figma app version into the skill's semver. Keep any installation cachebuster separate from the semantic release decision and align the full packaged version if one is added.
6. Update `SKILL.md`, UI metadata, root README, and CHANGELOG when their user-visible behavior changes. Set `compatibility.json` `skill_version` and the plugin manifest `version` identically. Synchronize the standalone source into the plugin with the repository tool, then run the relevant checks below once. Repeat only after related changes or failures.
7. Report sources/date, old→new skill version, affected operations, tests actually run, and remaining UI validation. Source completion, commit/push, installation, and new-session discovery are distinct. Perform release/install actions only within the user's request and the applicable workflow; do not claim the current session adopted a new installation.

## Repository validation

Run from the maintained repository root. Resolve `<skill-creator>` and `<plugin-creator>` to the actual skill directories exposed by the current environment; these are placeholders, not literal commands.

```text
python3 scripts/sync_skill_mirrors.py --write --package figma-computer-use
python3 <skill-creator>/scripts/quick_validate.py figma-computer-use
python3 <skill-creator>/scripts/quick_validate.py plugins/figma-computer-use/skills/figma-computer-use
python3 <plugin-creator>/scripts/validate_plugin.py plugins/figma-computer-use
python3 -m unittest scripts.tests.test_plugin_distribution scripts.tests.test_sync_skill_mirrors -v
python3 scripts/sync_skill_mirrors.py --package figma-computer-use
git diff --check
```

Distribution checks cover mirror bytes/modes, package-version alignment, dependency-free packaging, prompts, and relative references. They do not establish UI behavior. Review applicable scenarios against authorized resources:

| Change | Evidence required |
| --- | --- |
| Tool setup | Connect to the selected surface and read AX/screenshot without a design mutation |
| Selection/fields | Correct target and property readback after a requested change |
| Layout/components | Resulting hierarchy, bindings, size behavior, rendered output |
| Prototype | Requested interaction played from the intended flow |
| Export/save | Artifact inspected / visible cloud-save evidence, independently |

Use a fresh task to verify installed discovery only after installation is requested. Update this baseline from real outcomes, without turning untested scenarios into compatibility claims.
