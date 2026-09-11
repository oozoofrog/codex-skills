# Bundled consultation transport

The policy in `SKILL.md` chooses the objective, disclosure scope, surface, and exact live model/effort. `runtime/consult.mjs` executes that resolved contract through `runtime/cua-chatgpt.mjs`. It does not recommend models, create browser sessions, change the invoking Codex model/provider/configuration, open a server, or expose local tools to ChatGPT.

## Requirements and entry point

Use an authenticated tab obtained through the supported CUA browser API. Read that tool's documentation and inspect the current composer first. Import the bundled modules in the **same persistent CUA JavaScript session** that owns the tab. Resolve absolute module paths relative to the installed `SKILL.md`; standalone and Plugin copies contain identical runtime files. There is no standalone network CLI, MCP server, companion executable, profile migration, or extra npm dependency.

```js
// In the supported CUA JS session, after acquiring and inspecting `tab`:
const { consult } = await import('/absolute/installed/gptplease/runtime/consult.mjs');
const { ChatAdapter, WorkAdapter } = await import('/absolute/installed/gptplease/runtime/cua-chatgpt.mjs');
const request = {
  request_id: 'consult_unique_opaque_id',
  target: {
    surface: 'work',
    model: 'GPT-5.6 Luna',       // policy-selected, present in this live menu
    effort: '중간',              // exact observed UI label; not an internal protocol name
    selection: 'exact'
  },
  destination: { kind: 'new' }, // tab must already be a fresh https://chatgpt.com/ composer
  prompt: { text: 'The authorized objective, context, constraints, and requested deliverable.' },
  attachments: ['/absolute/path/to/authorized-file.json'],
  local_tools: 'disabled'
};
const adapter = request.target.surface === 'work' ? new WorkAdapter(tab) : new ChatAdapter(tab);
const run = consult(request, adapter);
nodeRepl.write(await run.start());  // inspect, configure, prepare and upload; never Send
nodeRepl.write(await run.poll());   // verify readiness/readback, attempt Send once, then read
```

Continue `poll()` in the invoking session until `returned_to_caller`, an actionable failure/input blocker, or caller cancellation. Use interruptible waits between running-response reads, initially about 15 seconds and then 30–60 seconds; do not busy-loop or block longer than 60 seconds. Every poll performs one read attempt. Three consecutive read exceptions stop automatic polling with `read_recovery_exhausted`; inspect the same tab before explicitly resuming. A long response that is still running is not a read failure and has no arbitrary short overall deadline.

An existing conversation requires `{kind:'existing', url:'https://chatgpt.com/c/REAL_ID'}` and a tab already at that exact URL. The runtime does not navigate or create a replacement. Do not substitute titles, sidebar positions, pending IDs, or Codex task IDs. Keep the surface of the existing conversation. `WorkAdapter` additionally requires the full Work model name in its composer; the Chat adapter uses the Chat composer signature. Unknown UI signatures fail before submission.

For settings-only requests, inspect the destination and use the adapter's `configure(target)` without creating a consultation or calling `prepare`, `send`, or `poll`. For keep-current requests, the policy first reads the current surface-specific settings and passes those exact labels. Automatic policy must resolve alternatives **before** calling this runtime; the runtime only accepts exact selections.

## Boundaries and preflight

- Pass only the exact approved file paths. No repository scan, context synchronization, secret scanner, approval receipt, or automatic file discovery runs here. Local path strings in the result are a manifest, not proof of uploaded bytes.
- Start on a clean composer. Existing drafts, file cards, removable attachments, and active generation block preparation. Recheck destination, baseline turn IDs, exact prompt paragraphs, surface, model, effort, and the full attachment manifest immediately before Send.
- Open the actual model submenu before interacting with a model. Current DOM snapshots can include **inert, collapsed** model entries. The adapter checks that the selected item is no longer inside an inert subtree; it never clicks an inert entry based only on its snapshot text.
- Model changes precede effort selection. Read the named level after each keyboard action. Do not enter the final Pro/Ultra tier merely to discover an unsupported lower level. A Pro account badge does not count as model/effort evidence.
- General file uploads use the visible add-files action and the supported file chooser. Register and handle the chooser promise before clicking. Wait for actual file cards, upload readiness, and matching removal controls; path text or pasted contents never substitutes for attachment. A zero-file manifest must remain empty through final preflight.
- A visible `[gptplease:REQUEST_ID]` marker is appended to the exact prompt for correlation. It is not a secret, authorization token, server idempotency key, or an exactly-once guarantee.
- `local_tools:'disabled'` is mandatory. The adapter accepts a browser handle only; it has no shell/filesystem/git callbacks and creates no ChatGPT-to-Codex tool bridge. ChatGPT's own cloud tools may process uploaded files. Returned advice never grants the caller new edit, push, publication, or disclosure authority.

## State and result

Normal flow is `prepared → configured → attachments_ready → send_attempted → delivery_unknown → delivery_confirmed → response_running/response_completed → response_retrieved → returned_to_caller`. A response can already be completed at the first successful read. Cancellation, terminal failure, and input-needed are separate outcomes.

`start()` never sends. The first eligible `poll()` marks `send_attempted` **before** the Send action. Any Send exception remains ambiguous; automatic resubmission and model/surface fallback are prohibited. Further polls only read. The same request ID is reserved on both first start and checkpoint restoration in that browser session. Do not use a new ID to work around an ambiguous attempt.

Results include requested and observed settings, conversation URL/real ID, attempted/confirmed delivery, actual user and assistant message IDs, attachment confirmations, response completion/Markdown/artifacts, error recovery flags, warnings, and the state history. Temporary `request-placeholder-*` assistant nodes do not establish response identity. Exact matching prompt plus marker must identify one new user turn; only its following assistant can complete the request. Multiple matches or an identity change fail closed.

Completion requires a final-answer control and no active generation, stable content in two reads, a copy of the **targeted** assistant turn, and a subsequent identity/content check. Clipboard contents, including non-text entries, are restored; an empty clipboard is handled explicitly. Copy text must retain all visible non-whitespace characters in order, including code operators and punctuation. This is a conservative UI consistency check, not cryptographic proof of server output. If it fails, `RESPONSE_TRUNCATED` leaves `response.complete=false`; recover by rereading the same answer.

`response.complete` covers the final Markdown and the artifact references exposed with it. Generated file buttons and `sandbox:` links are retained as file metadata; images and ordinary links retain their observed URLs. Empty file-link labels from Copy are filled from the observed filename. **Artifact bytes are not automatically downloaded**: `bytes_retrieved:false` remains explicit, and `sandbox:` URLs are scoped to the ChatGPT conversation, not local filesystem paths. If the user's requested processing depends on a file or image, open/read/download it through a supported tool and inspect it before claiming that processing is complete. Do not use a private endpoint to resolve it.

The invoking agent must also interpret ordinary final questions as requests for clarification when appropriate. A Work interaction that needs an approval or missing input must be brought back to the caller; do not click approval controls automatically. Adapter contracts can expose `needs_input`/`failed` for such response states. An unfamiliar interactive UI is an inspection blocker, not permission to resend.

See [recovery](transport-recovery.md), [account-bound validation](runtime-validation.md), and [response handling](response-return.md).

## Design provenance

The small direct-driver boundary was informed by [`codex-chatgpt-web` v5.0.6](https://github.com/miuuyy/codex-chatgpt-web/tree/v5.0.6), especially [`docs/dev-chat.md`](https://github.com/miuuyy/codex-chatgpt-web/blob/v5.0.6/docs/dev-chat.md) and [`src/dev-chat/driver.ts`](https://github.com/miuuyy/codex-chatgpt-web/blob/v5.0.6/src/dev-chat/driver.ts). This implementation uses the supported CUA session instead of that project's launcher, tunnel, provider, or browser-turn resend machinery. No source files from that runtime are vendored.
