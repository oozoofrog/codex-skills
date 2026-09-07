# Computer-use setup and observation

Read when starting or recovering a Figma UI session. These examples match `mcp__cua_repl.js` documentation observed on 2026-09-07. Current tool instructions are authoritative; another runtime may expose different signatures.

## Connect

On the first call or after `js_reset`, execute exactly one documented entrypoint and read its returned documentation/state before further calls.

- Named desktop app: `let figma = await cua.getApp("Figma");`. If name resolution fails, use the app inventory and retry with its returned bundle identifier. `com.figma.Desktop` was observed on macOS; do not assume every machine has it.
- Tab mention: `await cua.getState();`, match decoded provider tab ID, title, and URL, then call `cua.getTab` with returned tab/browser IDs.
- Known tab/browser: `let figma = await cua.getTab(tabId, { browser: browserId });`, using observed IDs.
- URL and named Chrome: `let figma = await cua.createBrowserTab("chrome", requestedUrl, { sessionName: "🎨 Figma" });`. Use `"edge"` for Edge. For `@Browser`, use `"iab"` with `{ visible: true }`.
- URL and no named browser: `let browser = await cua.getBrowser({ url: requestedUrl });`. Read its documentation, then use its returned `browserId` to create the tab in a later call with the provider's required options.
- No specified surface: `await cua.getState();`, then reuse a matching Figma tab or the available desktop app. Avoid duplicate file tabs.

`requestedUrl` is the user's real URL. For a desktop file link, use observed Figma navigation controls, or a supported browser for the same URL if permitted. Do not invent a native `goto` method. Browser selection alone does not open a tab.

## Observe and act

App and Tab targets support observations and UI input. Use only methods documented by the active runtime.

```javascript
// After connection. Observations emit their own output.
await figma.getAXStateAndScreenshot();
```

Choose indices from the latest accessibility tree. An AX index is an observation-local handle, not a Figma node ID. Coordinates are screenshot positions, not document X/Y values.

```javascript
// Resolve propertyIndex from the live tree and desiredValue from the task first.
await figma.click(propertyIndex);
await figma.setValue(propertyIndex, desiredValue);
await figma.pressKey("Return");
await figma.getAXState();
```

Batch only deterministic actions whose targets remain valid, then call `getAXState()` before the next decision. Selection changes can rebuild the properties panel; refresh before using its indices. After screenshot-only observation, request `getAXState({ disableDiffing: true })` before relying on AX indices again. Do not repeatedly request unchanged trees; use a screenshot/full tree when it resolves missing context.

Native Figma fields can display a new AX value without committing the document change when they were not focused. After an exact edit, leave the field and reselect the object; verify both the property and resulting geometry/rendering. In the 2026-09-07 test, an unfocused font-size field appeared to be 24 but reverted to 12 on reselection; focused input committed 24.

Some native AX spinbuttons ignore `setValue`, and a hex color exposed as a numeric spinbutton rejected `2563EB` with `invalidNumber("2563EB")`. Prefer the exposed color text/combobox control. If a numeric control remains unchanged, use a fresh screenshot to select its visible value, type it and commit, then read back the object. Do not keep retrying an ineffective setter. A frame drag also produced 1×1 in this test; correct the existing frame through verified width/height fields rather than creating another one.

For inaccessible canvas objects, obtain a fresh screenshot, click the visible target, and verify selection through Layers/properties before typing or changing values. Prefer exact property fields to estimated drags. A drag can reparent or reorder an Auto layout child; inspect hierarchy afterward.

`pressKey` uses xdotool-style syntax, such as `"Return"`, `"Escape"`, and `"super+c"`. Resolve uncertain Figma shortcuts from current menus/help. Check focus first: text editing, property fields, canvas, and browser chrome interpret keys differently. Do not paste a table of platform-specific shortcuts into every task.

Use `paste(text, { format: "text" })` for authorized multiline text into a confirmed text editor. Pasting arbitrary source into the canvas does not prove editable nodes were created. The observed native paste restores the previous clipboard; browser paste does not. Do not inspect unrelated clipboard content.

A clipboard timeout can occur after text was inserted: native Korean paste returned `Computer Use server error -10005: Timed out waiting for the application to read the clipboard`, while the intended text was present. Inspect the text before retrying to avoid duplicate content.

The runtime waits for observations, so avoid fixed sleeps before UI reads. `getScreenshot()` emits its image; do not wrap it in another emitter. Use only a documented output mechanism for a screenshot file and report only its real returned path.

## Capability failures

If the active runtime lacks upload/file-picker or download-result support, do not invent `uploadFile`, `download`, clipboard readers, or CUA filesystem APIs. Use other documented file tools only within their authorization. Report an export as unverified when the output cannot be inspected. Never bypass a UI limitation using private APIs or another automation stack.

When a native file picker is exposed, use its current AX controls and supported keyboard navigation. On macOS, Go to Folder (`super+shift+g`) can select an authorized path; verify the resulting filename/folder and enabled Open/Save button. A PNG export of `QA / Start` opened a folder chooser and produced `QA/Start.png` under that folder. Check actual output paths rather than assuming a filename field or a flat output directory.

After a native pipe/app-server error, reselect the app through the documented entrypoint and inspect the same file. A supported browser fallback may have a separate login session. If a tool timeout resets the JavaScript kernel, start again with exactly one entrypoint; previous bindings no longer exist. In this test the native connection recovered after a kernel reset without restarting Figma, while IAB was logged out and Chrome could not attach. Stop repeating the same failed attachment when no state has changed; report that surface separately. Reconnection alone does not prove cloud saving.
