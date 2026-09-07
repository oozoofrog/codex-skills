# Manual source register

Reviewed 2026-09-07. Official articles were opened and read, not merely listed from search results. The internal manual contains task-oriented paraphrases; it does not bundle copyrighted manuals or rely on local source files at runtime.

## Official web manuals

| ID | Source | Internalized guidance |
| --- | --- | --- |
| S1 | [Explore design files](https://help.figma.com/hc/en-us/articles/15297425105303-Explore-design-files) | Navigation, selection-dependent panels, permission-aware inspection |
| S2 | [Frames in Figma Design](https://help.figma.com/hc/en-us/articles/360041539473-Frames-in-Figma-Design) | Parent/child structure, frame creation, dimensions, clipping |
| S3 | [Guide to auto layout](https://help.figma.com/hc/en-us/articles/360040451373-Guide-to-auto-layout) | Flow, padding/gap, per-axis Hug/Fill/Fixed, numeric resizing side effects, Ignore auto layout |
| S4 | [Guide to components](https://help.figma.com/hc/en-us/articles/360038662654-Guide-to-components-in-Figma) | Main component and linked instance scope |
| S5 | [Explore component properties](https://help.figma.com/hc/en-us/articles/5579474826519-Explore-component-properties) | Text/boolean/swap/variant/slot properties, state consolidation and prototype connections |
| S6 | [Variables, collections, and modes](https://help.figma.com/hc/en-us/articles/14506821864087-Overview-of-variables-collections-and-modes) | Bindings, modes, aliases, plan-dependent availability |
| S7 | [Guide to prototyping](https://help.figma.com/hc/en-us/articles/360040314193-Guide-to-prototyping-in-Figma) | Flows, starting points, edit versus playback access |
| S8 | [Export static designs](https://help.figma.com/hc/en-us/articles/360040028114-Export-static-designs-from-Figma) | Selection/slice/page/file scope, owner restrictions, export settings |
| S9 | [Offline behavior](https://help.figma.com/hc/en-us/articles/360040328553-What-can-I-do-offline-in-Figma) | Offline edits versus cloud save, preserve unsynced state |
| S10 | [Product release notes](https://www.figma.com/release-notes/) | Product-change tracking; latest entry observed was 2026-09-03, Control opacity at scale |

Official Help Center also links to `https://releases.figma.com/`. Opening that release archive returned `URL https://releases.figma.com/ is not safe to open (non-retryable error)` in the research tool on the review date. Its contents and latest desktop release were not verified; do not treat it as evidence that the installed app is current. Revisit only through a supported tool when necessary, without bypassing a security block.

## Local manuals and observations

Search covered local skill directories, plugin caches, Documents/Codex, Documents/ChatGPT, and Markdown/manual filenames in local development checkouts. An initial broad Documents search encountered broken CrossOver symlinks; the targeted search completed. This is a scoped search, not a claim that every local file was inspected.

Paths below identify research provenance, not installation dependencies. On another machine, locate an equivalent source by filename/title; missing local files do not block the self-contained manual.

| ID | Local source | Assessment and incorporation |
| --- | --- | --- |
| L1 | Live `mcp__cua_repl.js` documentation and native Figma UI, 2026-09-07 | Used for connection, observation/input APIs, fresh indices, screenshot fallback, clipboard differences. Authorized draft testing covered native edits, components, variables, prototype navigation/back, PNG export and import. Focus, numeric-input, timeout and recovery findings are internalized in [computer-use setup](computer-use.md); exact scope and gaps are in [runtime validation](runtime-validation.md). |
| L2 | `/Applications/Figma.app/Contents/Info.plist` | Bundle ID `com.figma.Desktop`, short/build version `126.8.18`; local metadata only, not a web editor version. |
| L3 | `/Volumes/eyedisk/develop/oozoofrog/Unicody/.claude/skills/moai-design-tools/reference/figma.md` — Figma MCP Implementation Guide, dated 2026-02-09 | Retained the useful inspection categories: semantic tokens, component hierarchy, and documented states. Re-expressed them as UI inspection. Excluded MCP/PAT/API/CLI examples and automatic publishing/committing; these are neither current UI documentation nor authority for this task. |
| L4 | `/Volumes/eyedisk/develop/oozoofrog/oozoofrog-plugins/plugins/design-craft/skills/design-audit/references/designs/figma.md` — Design System Inspired by Figma | Website visual-style analysis, not an editor operation manual. Do not apply its fixed font/color/button rules to arbitrary user designs. |
| L5 | `/Volumes/eyedisk/develop/oozoofrog/awesome-design-md/design-md/figma/DESIGN.md` — Design System: Figma | Same kind of marketing-site style guidance; inspected for relevance, excluded from operational defaults. |

Local snapshot SHA-256 values, for recognizing changed research inputs during maintenance:

- L3: `150d2adfd9cd980cf3ebcca99147a542b3c2808e02123c42690e25981c731747`
- L4: `300e3f8c432bd19e14cf530ec546b9ead3a6113ada0e0ad67616da43de774a81`
- L5: `d91d11f0290bc0d1f5f55bd408aa3959291079bd4c105dfa130df8e931ebca48`

No MoAI or design-audit workflow was invoked; these documents were read as reference data. Local guidance must be checked against current official manuals and observed UI before becoming an operating rule.
