# Security boundary

## Desktop connection

- Accept only credential-free loopback HTTP discovery and the loopback CDP WebSocket target.
- Verify that the listener belongs to the current user, `/Applications/ChatGPT.app`, the exact gptpro Runner profile, and port 9223.
- Attach only when exactly one renderer has `type=page` and `url=app://-/index.html`.
- Forward signed response sockets only through the attached renderer and only to credential-free `wss://ws.chatgpt.com` URLs returned for the exact handoff topic.
- Start port 9223 only on loopback for the isolated Runner; never expose it through LAN forwarding, SSH tunnels, containers, or public interfaces. The ordinary ChatGPT process does not need a debugging port and may remain open normally.
- The optional `~/Applications/gptpro Launcher.app` starts the isolated process/profile but installs no daemon or Login Item, never terminates either ChatGPT process, and does not replace the governed `desktop-doctor` checks.
- The Runner never copies the ordinary ChatGPT profile, cookies, tokens, or Keychain values. If the separate profile requires login, the user completes it inside the Runner UI.

## Disclosure

The exact `outbound.md`, not a ZIP or live repository, is sent. Preparation rejects unsafe paths, symlinks, non-UTF-8 data, disallowed untracked files, detected secrets, boundary collisions, and output above 262,144 bytes. Verification checks every inline header, body size, body hash, and the final outbound hash.

Selected Git filenames are always literal pathspecs. Repository reads walk each parent directory from the repository descriptor with `O_DIRECTORY | O_NOFOLLOW` and open the final file relative to that descriptor; an ancestor symlink cannot substitute outside content. HEAD-relative deletions remain selectable before and after staging, including deletion-only file lists. They use the same include/exclude and secret-path rules, and their patch content is secret-scanned. Deleted paths are recorded in the manifest's `diff.deleted_paths` and the inline diff header's `deleted_paths`, count toward the file limit, and participate in standing approval path checks. Existing Schema-6 packages without this optional field retain their original verification format.

Approval binds the exact manifest, outbound and system-prompt hashes, model, `desktop-electron`, normal Chat, and inline format. Immediately before POST, the child reports the bytes it read and waits for the parent to re-verify approval and durably record `submission_dispatching`.

The send boundary has three simple states:

- Before `submission_dispatching`: no POST was authorized. A verified capability failure may be retried while the same approval remains valid.
- At `submission_dispatching`: the package becomes permanently no-resend before the child receives permission to POST.
- After that boundary: gptpro accepts the primary response only after the POST handoff's authenticated subscription, recovered catchups, ordered stream items, and terminal `done`. Missing response evidence does not prove that nothing was sent. Use explicit GET-only `collect-response` or inspect normal Chat; never resend the old package automatically.

State and receipt are both retained deliberately. State provides the current lifecycle decision; the hash-chained receipt proves how that decision was reached after a crash.

No local function, server-tool fallback, MCP, shell, build/test, file write, Git mutation, arbitrary filesystem, or arbitrary network tool is exposed. Any explicit assistant recipient other than `all` fails closed, and a completed assistant response must prove `recipient=all`. A branch-ambiguous tool-role status is never allowlisted by author name or metadata. A tool-role candidate, pre-handoff assistant evidence, or signed delta that continues pre-handoff state requires signed completion followed by an authenticated exact current-branch GET bounded to 30 seconds. Ambiguous post-authorization state is never resent automatically.

## Credentials and output

The runtime intentionally does not read cookies, passwords, MFA codes, OAuth/session tokens, Authorization values, or unrelated renderer storage. Signed-stream completion binds one topic, conversation, turn, parent chain, terminal `done`, final assistant text and message identity, and `recipient=all`; receipts retain only a topic hash, never the raw topic or signed URL. Conditional branch proof uses only the known conversation ID, deterministic user message, current branch, and signed assistant ID/text; it neither lists conversations nor changes the signed completion source. GET-only recovery accepts only one conversation branch whose deterministic message ID and outbound bytes match. Unrelated conversation titles and contents are not persisted or emitted. Raw request and conversation identifiers are not stored; receipts contain hashes. Raw and wrapped responses are stored separately, and model output remains untrusted until Codex validates it.
