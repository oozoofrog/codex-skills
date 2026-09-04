---
name: swift-intelligence
description: Use the global Swift Intelligence MCP tools to navigate and inspect Swift code semantically. Apply for Swift definitions, references, protocol implementations, compiler-resolved types, document symbols, workspace symbols, and diagnostics; do not use for plain text or resource-file searches.
---

# Swift Intelligence

## Workflow

1. Pass the absolute repository root as `workspace_path` on every call.
2. At an Xcode root, call `swift_xcode_schemes` first. If `selectionRequired` is true, present `schemes` to the user, ask which one to use, and pass that answer as `xcode_scheme` on every semantic call. Do not choose an arbitrary scheme.
3. If only a symbol name is known, locate one source occurrence with repository search or `swift_workspace_symbols`.
4. Convert the source location to zero-based `line` and UTF-16 `character` values.
5. Call the narrowest matching tool:
   - `swift_definition` for the declaration owning a use.
   - `swift_references` for symbol-accurate uses.
   - `swift_implementations` for protocol or method implementations.
   - `swift_hover` for compiler-resolved type and documentation.
   - `swift_symbols` for declarations in one file.
   - `swift_workspace_symbols` for indexed symbol discovery.
   - `swift_diagnostics` for compiler diagnostics.
   - For exhaustive protocol-requirement results, combine its `swift_references` and `swift_implementations`, then run `swift_references` on each implementation; these are separate semantic relations.
6. Use text search as a fallback or cross-check and label lexical results as lexical.

## Constraints

- Prefer a path relative to `workspace_path` for `file_path`.
- The MCP tools are read-only. Edit files only after reviewing their results.
- Build the relevant Xcode or SwiftPM target before relying on cross-file results.
- At an Xcode repository root, the server selects the sole `.xcworkspace` or `.xcodeproj`. It uses a same-named shared scheme automatically; otherwise `xcode_scheme` is required. Multiple containers are an explicit error.
- `SWIFT_INTELLIGENCE_XCODE_SCHEME` remains a default for fixed automation. Per-call `xcode_scheme` takes precedence. Both accept a comma-separated list: `-showBuildSettingsForIndex` only covers targets in a scheme's build action, so list the app scheme plus per-module schemes to reach framework sources. When a file is outside every selected scheme, a path component that names a shared scheme (for example `Projects/TalkMediaKit/...` → scheme `TalkMediaKit`) is merged into the same session automatically; the first such call restarts sourcekit-lsp (about a minute). Files with no matching scheme still fail with `build settings do not include`. Each scheme costs about a minute once; index settings are cached under `~/Library/Caches/swift-intelligence/` and refresh when a `project.pbxproj` in the workspace changes. The IndexStoreDB database also lives there, one per index store, so a restarted server reopens it incrementally instead of re-importing every unit; a second live server on the same store falls back to a temporary database. Set `SWIFT_INTELLIGENCE_EXPLICIT_UNITS=1` to restrict the index to units of the loaded targets' own files: this removes stale positions left by units of other configurations (Sandbox, SampleApp), but references inside modules that are not in the selected schemes disappear, so keep it off unless every module you query is listed. `xcodebuild -showBuildSettingsForIndex` ignores `-configuration`, so if the emitted product paths name a configuration you never built, set `SWIFT_INTELLIGENCE_XCODE_CONFIGURATION` to the one you did build and its `<config>-<sdk>` path components are rewritten.
- An empty indexed result is inconclusive when build settings or the SourceKit index are unavailable.
- Do not claim exhaustive references after an error, timeout, or missing build settings.
