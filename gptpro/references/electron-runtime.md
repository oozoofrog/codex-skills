# Private Electron compatibility boundary

This clean-room runtime was informed by observed behavior in the supplied Pi extension archive; it does not copy its non-`ws` source. The non-`ws` redistribution license was not established. Node 22's built-in WebSocket handles CDP; no dependency is vendored.

Private assumptions are isolated under `runtime/chatgpt-desktop/`:

- exact `app://-/index.html` renderer;
- renderer-to-main `connect-app-host` MessagePort RPC;
- app-host `httpFetch.fetch/cancel`;
- Desktop environment and DeviceCheck;
- live model catalog, attestation, conversation POST, current Chat turn selectors, recent-conversation list, and conversation-detail formats.

These are not public OpenAI API contracts. `probe` sends no conversation, `models` uses only the logged-in live catalog, and `ask` accepts one strict UTF-8 message of at most 262,144 bytes. The payload contains no local function signatures and uses normal Chat.

## Isolated Runner

`launcher-install` creates `~/Applications/gptpro Launcher.app` from deterministic standard-library assets. The launcher contains only an `Info.plist` and a small zsh executable. It starts a second process from the installed, signed `/Applications/ChatGPT.app` with `--user-data-dir=~/Library/Application Support/gptpro/runner/v1/profile`, `--remote-debugging-address=127.0.0.1`, and `--remote-debugging-port=9223`. The ordinary ChatGPT process and profile are not inspected, stopped, or relaunched.

The separate profile is owner-only and may require one attended login if the Desktop app does not reuse the account's system credential state. The runtime never copies credentials from the ordinary profile. `desktop-doctor` requires the exact profile and port arguments on the listening current-user ChatGPT process, then verifies the target, bridge, environment, and DeviceCheck. An unrelated listener on port 9223 is rejected.

This is process/profile isolation, not a redistributed ChatGPT clone. It avoids changing the ordinary app's execution environment without copying proprietary renderer assets or reimplementing authentication. An explicit alternate CDP endpoint is retained only for development diagnosis and is not used by normal consultations.

Install and uninstall use one owner-only nonblocking file lock. A new install uses macOS `RENAME_EXCL`; an update uses `RENAME_SWAP`, verifies the exact pre-swap bundle identity, and moves the prior managed bundle to Trash. A cleanup failure leaves the new launcher installed and returns a recovery path instead of deleting unverified data. Cross-filesystem Trash moves fail before mutation. Process inspection has an explicit unknown state and never opens another ChatGPT instance when inspection fails.

One monotonic deadline covers attestation, POST response headers, and authenticated response readback. The current Desktop rejects the archive's `sendMessageFromView` HTTP path and requires app-host `httpFetch`. After POST headers, the runtime polls conversation GETs through the same app-host service while the original reader remains open. The GET result must prove the deterministic user-message ID, exact outbound body, successful final assistant turn, and zero tool routes before the original reader is released.

Normal `consult` uses exact-message conversation readback as its primary completion path. Standalone `collect-response` is the same GET-only correlation used as a recovery path after process interruption or automatic capture failure and never sends a prompt. Progress exposes only fixed content-free stages. On failure, receipts keep the last stage but not prompts, tokens, raw request/conversation IDs, or renderer state. A correlation, endpoint, or tool-route violation fails closed instead of selecting another renderer, model, or transport.
