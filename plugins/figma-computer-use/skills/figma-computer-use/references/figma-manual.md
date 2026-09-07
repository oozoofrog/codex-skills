# Internal Figma operation manual

Distilled operating rules, not a copy of the vendor manual. Read only the task-relevant section. Sources and review date are in [sources](sources.md); version drift is handled in [maintenance](maintenance.md). Live labels and permissions determine which controls are available.

## Navigate and inspect — sources S1, L1

Use file navigation and the left sidebar to resolve pages/layers; use Assets for reusable components. The right sidebar describes the current selection and access level. Design and Prototype controls are available for editing; view-only presentation does not prove edit access. Toolbar position can change between releases, so find controls by observed identity rather than screen edges.

For reviews, inspect the full rendered frame and relevant Layers/properties controls without editing or duplicating anything. Read exact type, spacing, dimensions, colors, and bindings from exposed properties; label visual estimates. Check whether the selection is an instance or main component before recommending a change.

## Build frames, text, and layout — sources S2, S3

1. Create a clearly named frame with the requested dimensions. Build major content groups, then text and controls using native layers; a pasted screenshot is not an editable screen. Preserve supplied wording and reuse relevant styles/variables/components.
2. Select one object and read its properties before precise edits. When entering or leaving text editing, recheck focus and selection. Verify content, font availability, wrapping, clipping, and final geometry. Resolve a missing font instead of silently substituting it.
3. For Auto layout, inspect the parent and child settings: horizontal/vertical/grid flow, alignment, gap, padding, and each axis's sizing. Hug fits an Auto layout frame to its children; Fill occupies available parent space and applies to children of Auto layout frames; Fixed keeps the dimension. Entering numeric width/height can change the axis to Fixed. Read behavior back after editing.
4. Auto layout controls placement; a drag may reorder/reparent rather than merely change coordinates. Inspect hierarchy afterward. Use the live Ignore auto layout control only when free placement is intended; older manuals may call it absolute position.
5. Review at a readable zoom for alignment, overflow, contrast, and requested states. For responsive work, exercise requested sizes and verify reflow, then restore intended final dimensions.

## Components, variants, and properties — sources S4, S5

A main component defines shared design; instances stay linked and receive its updates. Choose instance properties for local changes and main-component edits only when the requested shared effect is in scope. Do not detach/flatten to bypass a property limitation.

Use text properties for content, booleans for exposed layer visibility, instance swap for interchangeable nested instances, and variant properties for defined alternatives such as state/size. Current documentation also describes slot properties for flexible component content; inspect actual availability before using them. Variants belong to a component set. Do not assume an ordinary component has variant controls.

When consolidating states, preserve prototype connections: replacing distinct interactive objects with one boolean visibility property can remove the objects that connections need. Check selected instances, overrides, and final behavior. Before multi-edit, confirm every selected layer is intended; mixed values are not one verified property.

## Variables and styles — sources S6, S10

Preserve an existing variable/style binding when changing a value or choosing a mode. Inspect the bound property and active mode rather than treating a displayed color as a standalone hex value. Apply only collections/modes available in the file and account. Never publish or change a shared library solely to fix a local instance.

The 2026-09-03 release notes describe applying opacity through variables while retaining color links. If requested and exposed in the live UI, prefer that binding-preserving operation to detaching a color. This is documented capability, not a feature verified in the local editor. For related releases, use the source register and refresh only the affected guidance.

## Prototype — source S7

Confirm source/destination frames and the intended starting point. Use live Prototype controls to set trigger, action, transition, and flow. Read them back, then open presentation and exercise each requested interaction, including required back/close behavior. Multiple flows can exist on a page. A connection line proves configuration only; behavior needs playback evidence. Return to the editor when further work is required.

## Import and export — source S8

Import only authorized assets into the intended file through supported UI/file controls, then confirm resulting layers and placement. Upload, pasted text, and pasted vector content are distinct results.

For export, select the exact requested layers/frames, verify format/scale/name/location, then export. Export scope can include selections, a slice, a page, or a file copy; deselecting everything can target a whole page. View access may permit export unless the owner restricts copying/sharing. A blocked export is not permission to bypass those restrictions.

Inspect the actual saved/downloaded artifact using supported tools; check format/dimensions and render when possible. Settings or a button click do not prove a file exists. Report only an observed output path. Do not derive a node URL from an AX index.

## Save, recover, and hand off — source S9

Inspect final rendering and visible save/sync status. Figma can retain offline edits and sync on reconnection; pending/offline edits are not proof of cloud persistence. Keep the session open when saving is unresolved; do not clear state or reload to test saving.

After a timeout, inspect the same file for a completed paste/create/export before retrying. If selection is ambiguous, resolve it before another edit. Undo only an attributable action with no intervening collaborator change; otherwise make a targeted correction.

Hand off the actual file/page/frame, observed URL if available, and a final frame screenshot. Distinguish exact property readback, visual quality, save status, played prototype interactions, and inspected export evidence according to the request.
