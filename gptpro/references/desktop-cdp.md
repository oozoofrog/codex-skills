# ChatGPT Desktop CDP delivery

`desktop-cdp` is an optional attended delivery channel for macOS. It sends one already-approved textual handoff through the signed-in ChatGPT Desktop app and captures one advisory response. It does not replace `gptpro.py` repository selection, secret scanning, hashes, approval, receipts, import, or independent evaluation.

Phase 1 targets macOS, an Apple-silicon ChatGPT Desktop build with DeviceCheck support, and Node.js 22 or newer with a built-in WebSocket implementation. The private Desktop contract is best-effort and may change without notice. It is not the public OpenAI API.

## Start an explicit debug-enabled instance

The Skill detects and explains; it does not kill or relaunch ChatGPT. The user may explicitly start a separate instance when needed:

```bash
open -na "/Applications/ChatGPT.app" --args --remote-debugging-port=9222
```

Port 9222 gives powerful local automation access to the renderer. Use only loopback, only while needed. Do not expose it through an SSH tunnel, container mapping, LAN forwarding, or a public interface. Close the debug-enabled ChatGPT instance after consultation. Localhost access is not harmless on a compromised machine.

Phase 1 accepts only parsed loopback endpoints (`127.0.0.1`, `localhost`, or `::1`), rejects URL credentials and non-HTTP(S) discovery, validates a loopback debugger WebSocket, and attaches only to exactly one `page` target whose URL is `app://-/index.html`. Target drift fails closed.

## Lifecycle

Prepare a package with a separate context transport and delivery channel. `paste` is the most direct Desktop phase-1 transport because its single outbound message already contains the selected repository text. `github` remains available when the signed-in ChatGPT experience can access the approved immutable snapshot. `text-file` is rejected with `desktop-cdp` in phase 1 because this runtime does not upload attachments.

```bash
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode review \
  --transport paste \
  --delivery-channel desktop-cdp \
  --task "Review the current change."

python3 <skill-dir>/scripts/gptpro.py verify --handoff-dir <dir>
python3 <skill-dir>/scripts/gptpro.py status --handoff-dir <dir>
```

Show the exact outbound message, transport, delivery channel, Git identity, exclusions, and hashes. Obtain package-specific approval, then record it with `approve`. A successful probe is not approval to send.

Probe without creating a conversation:

```bash
node <skill-dir>/scripts/chatgpt-desktop.js probe
```

The normalized result reports only the loopback endpoint, exact target URL, bridge/DeviceCheck/chunk/environment capability booleans, and sanitized app version. It intentionally does not expose cookies, tokens, auth headers, attestation values, app session IDs, device identifiers, or unrelated renderer state. An existing Desktop-owned `oai-did` is used only inside renderer-originated request headers and never returned to Node or persisted by this runtime.

Read the live signed-in model catalog:

```bash
node <skill-dir>/scripts/chatgpt-desktop.js models
```

The result is labeled `source: "dynamic"` and scoped to selectable public options derived from active Desktop categories/version presets; raw backend metadata, disabled entries, and internal groups are not presented as account entitlement. Resolve the approved human-facing model intent to exactly one live backend `id` and supported `thinking_effort`. If no candidate or more than one candidate matches, stop and show the candidates; do not silently select a fallback. There is no static entitlement fallback in phase 1.

Show the resolved id/effort and obtain an explicit user confirmation, then bind that selection to the approved handoff:

```bash
python3 <skill-dir>/scripts/gptpro.py approve-desktop-model \
  --handoff-dir <dir> \
  --approved-by user \
  --model-id <exact-live-backend-id> \
  --thinking-effort <exact-supported-effort> \
  --confirm-live-catalog
```

Omit `--thinking-effort` only when the confirmed selection has no explicit effort. Changing this selection requires running the same explicit confirmation step again before submission; `ask` rejects a mismatch before opening CDP.

Send the single approved message. For `paste`, use the `paste_payload_path` and its hash. For `github`, use `prompt_path` and its hash. Supply the manifest SHA-256 shown by verification:

```bash
node <skill-dir>/scripts/chatgpt-desktop.js ask \
  --handoff-dir <dir> \
  --prompt-file <approved-message-path> \
  --prompt-sha256 <approved-message-sha256> \
  --manifest-sha256 <approved-manifest-sha256> \
  --package-id <package-id> \
  --model <exact-live-backend-id> \
  --thinking-effort <exact-supported-effort> \
  --output <dir>/desktop-response.md \
  --raw-output <dir>/desktop-response.raw.md \
  --result-file <dir>/desktop-result.json
```

Before opening CDP, `ask` calls the existing Python governance CLI's read-only `desktop-authorization` command. It must prove that the package is still exactly `approved`, its selected channel is `desktop-cdp`, and the prompt path/hash is the sole approved message artifact. A manually assembled prompt or merely successful probe is rejected before connection. All three output files must be distinct, new files directly inside that handoff directory; an existing target fails before submission to avoid overwrite or accidental duplicate-send behavior.

Fresh conversation is the default and the only documented phase-1 mode. The request explicitly sends `local_function_signatures: []`; ChatGPT cannot invoke local shell/filesystem tools through this runtime. Timeout or cancellation sends a cancellation message. The runtime never retries an interrupted or ambiguous conversation automatically.

After success, bind the generated result and response hashes to the existing state machine:

```bash
python3 <skill-dir>/scripts/gptpro.py mark-submitted \
  --handoff-dir <dir> \
  --observed-transport paste \
  --observed-channel desktop-cdp \
  --observed-model <exact-live-backend-id> \
  --desktop-result <dir>/desktop-result.json \
  --confirm-sent

python3 <skill-dir>/scripts/gptpro.py import-response \
  --handoff-dir <dir> \
  --response-file <dir>/desktop-response.md
```

The runtime stores the exact decoded visible assistant body without trimming or a synthesized citation appendix, then wraps it deterministically with the package-specific response markers. Decoded source metadata remains separate in the result file. The result records both hashes, `marker_origin: "runtime"`, approved model/effort, conversation/message identifiers when available, proof that local function signatures were empty, and the completion evidence.

Current Desktop stream handoff can end with a Desktop-owned successful transport-complete event without a separate backend `message_stream_complete` event. The runtime accepts that path only after the bridge has opened the stream successfully, the iterator closes normally, at least one normal assistant message was decoded, no explicit non-success assistant status remains, and visible output is non-empty. A `message_stream_complete` event or `finished_successfully` assistant status is recorded when present. Bridge errors, cancellation, timeout, abrupt iterator failure, tool-only output, and explicit unfinished status still produce `STREAM_INTERRUPTED` or their stable error. `desktop-result.json` records `transport_complete`, `completion_signal`, `assistant_message_observed`, and optional `assistant_message_status`; `gptpro.py` validates them together with all hashes and wrapper bytes before changing the phase. It will import only the wrapper already bound to the Desktop submission receipt.

## Private compatibility boundary

All unstable assumptions are isolated under `runtime/chatgpt-desktop/`: `window.electronBridge`, Desktop IPC and chunking, `/models?iim=false&include_icons=false`, `/ios/attestation_challenge`, `/f/conversation`, Desktop-owned auth/integrity attachment, and the streamed delta format. The implementation uses the Desktop bridge so the app owns authentication and attestation; it does not intentionally read or persist session material. Chunk frames are reassembled inside the renderer and only a completed response whose request id is active is forwarded over the CDP binding. The runtime relies on the Desktop renderer's existing chunk receiver for acknowledgements and fails on capability/protocol drift rather than forwarding unrelated completed responses.

The runtime is a clean-room implementation of observed behavior. The separately described Pi archive was not redistributed because provenance and a redistribution license for its non-`ws` source were not established. No Pi provider adapter or Pi API types are included. No third-party `ws` copy is vendored; the runtime uses Node's built-in WebSocket and has no npm install step.

## Failure and human action

Stable failures include `CDP_UNAVAILABLE`, `CDP_ENDPOINT_REJECTED`, `TARGET_NOT_FOUND`, `BRIDGE_UNAVAILABLE`, `DESKTOP_CAPABILITY_UNAVAILABLE`, `DEVICE_CHECK_UNAVAILABLE`, `MODEL_CATALOG_FAILED`, `MODEL_NOT_FOUND`, `MODEL_AMBIGUOUS`, `MODEL_EFFORT_UNSUPPORTED`, `CONVERSATION_REJECTED`, `STREAM_PROTOCOL_ERROR`, `STREAM_INTERRUPTED`, `TIMEOUT`, and `CANCELLED`.

For a launch, login, account/workspace, CAPTCHA, model ambiguity, or capability boundary, use `human-handoff --reason desktop-capability` or the more specific listed reason. Human help does not authorize transmission. If `desktop-cdp` fails after channel-specific approval, keep the package `approved` and report the failure. Browser or manual delivery requires a newly prepared and approved handoff; never silently fall back or resend after an ambiguous submission.

To avoid Desktop CDP entirely, prepare with `--delivery-channel browser` or `manual` and follow [browser-handoff.md](browser-handoff.md) and [human-takeover.md](human-takeover.md).
