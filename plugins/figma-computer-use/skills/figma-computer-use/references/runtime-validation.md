# Observed runtime validation

2026-09-07; Figma desktop `126.8.18`, macOS, Korean UI, `mcp__cua_repl.js`. User explicitly requested full skill verification, authorizing a dedicated QA draft. All Figma interaction used computer-use. Filesystem tools inspected the exported artifact and maintained this package.

This is representative coverage of the skill's operation categories, not exhaustive certification of every Figma feature, platform or plan. Test source changes are packaged as `0.1.1`; installing that version and discovering it in a fresh task remain separate.

| Area | Observed result |
| --- | --- |
| Connection/inspection | Native app connection, file/page selection, AX and screenshot observation passed; browser editing did not complete. |
| Native design | New named draft; two 400×360 frames; Korean text, exact font size/color, text style; duplication, layer rename and reparenting passed. |
| Auto layout | Horizontal Hug button 117×43, horizontal/vertical padding 24/12, gap 10, corner radius 8 read back. Fixed outer frame dimensions passed. Fill/responsive reflow and grid were not exercised. |
| Components | Main component, State=Primary/Secondary variants, Assets insertion, instance state switching and reparenting passed. Text/boolean/swap/slot properties were not exercised. |
| Variables/styles | Local QA/Primary color variable 2563EB and bound fill, local QA/Heading text style 24/Auto passed. Modes, aliases, opacity-variable binding and shared library publishing were not exercised. |
| Prototype | On click → Navigate to QA / Done, and On click → Back, configured and played using the actual instance buttons. Frame content and URL changed and returned. |
| Export | PNG 1x exported through the native folder picker; actual 400×360 artifact and rendering inspected. SVG/JPG/PDF/file-copy exports were not exercised. |
| Import | Exported PNG selected in native file picker and placed on QA Imports as a 400×360 rectangle; rendering inspected. Native editable source layers remain on Page 1. |
| Save | Version history displayed a 22:56 entry, but a named-version save attempt did not show the submitted title afterward. Cloud persistence and named-version save remain unresolved; no reload/close was used to force a save test. |
| Recovery | Korean paste completed despite clipboard timeout; inspected before retry. Native connection recovered after a tool kernel reset and the same file remained accessible. |

Confirmed input pitfalls and supported recovery are maintained in [computer-use setup](computer-use.md). A native connection outage returned `Sky Computer Use native pipe closed before response` and `Computer Use server error -10005: codex app-server exited before returning a response`. The supported IAB fallback showed an expired/login-required session. Chrome creation returned `Timed out after 10000ms waiting for CDP command Accessibility.enable.` and selecting that existing tab timed out with `js execution timed out; kernel reset, rerun your request`. These are tool-reported errors; no direct CDP or alternate automation was used. Do not generalize the native pass to browser support.

Revalidate only the requested operation and relevant unresolved cases when the environment changes. Do not create a new QA file on every normal invocation.
