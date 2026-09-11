# Consultation recovery

Retain the run object while working. `run.snapshot()` returns the exact local request, submitted prompt, baseline IDs, and last evidence. Treat it as private caller context: it can contain authorized file paths and prompt contents. Do not commit it, send it to ChatGPT, or log login/session data alongside it. The runtime does not write durable state or create a background process.

- Before Send: `await run.cancel()` prevents submission. After the current operation has settled, `await run.cleanup()` clears only the exact owned prompt. Uploaded attachments remain explicitly uncleaned for supported UI removal; cleanup is not claimed complete while they remain. Configuration may already have changed. Preserve unrelated drafts and files.
- After Send: cancellation stops local waiting/collection and preserves delivery/identity evidence. It does not assert that ChatGPT stopped generation and does not click Stop. Never recreate the request to resume.
- Resume a retained run with `await run.resume()`. This is read-only and cannot Send. A cancelled unsent run cannot resume into a submission.
- After a CUA reset, reacquire the same known tab through the supported browser API and import the bundled modules. Restore using `consult(checkpoint.request, adapter, checkpoint)` and then `resume()`. Only a matching attempted submission is accepted. Restoration reserves its request ID in the new session as well. If the old state or conversation cannot be established, report an unresolved delivery state; do not send a replacement.
- Runtime reload/process restart without a checkpoint loses the session-local registry. There is no durable global exactly-once guarantee. Request markers assist correlation only. Follow the caller's existing continuation mechanism to retain the known conversation and no-resend obligation.

| Error or state | Allowed response |
| --- | --- |
| `AUTH_REQUIRED`, `SURFACE_UNAVAILABLE`, `MODEL_UNAVAILABLE`, `EFFORT_UNAVAILABLE` | Resolve access or ask policy for a newly authorized exact configuration before any submission. |
| `CONFIGURATION_MISMATCH`, `ATTACHMENT_FAILED`, `UI_DRIFT` before Send | Inspect the current composer. Keep the request unsent; never silently paste files or switch models. |
| `delivery_unknown` / `DELIVERY_UNKNOWN` | Read only the same originating tab/conversation and find the exact received user turn. An empty composer is not proof of rejection. |
| `response_running` | Wait interruptibly and read again. |
| `needs_input` / `RESPONSE_NEEDS_INPUT` | Surface the exact required choice to the caller; the response does not grant approval. |
| `RESPONSE_FAILED`, `TURN_IDENTITY_AMBIGUOUS` | Retain evidence and inspect. No automatic new submission. |
| `response_completed` / `RESPONSE_TRUNCATED` | Retrieve the rest or re-copy that exact final turn. Completion alone is not retrieval. |
| Three consecutive read exceptions | Stop automatic recovery; inspect before explicit `resume()`. |
| `CANCELLED` | Report whether Send was attempted and whether physical cleanup completed. Resume only on explicit continuation. |

`automatic_new_submission:false` is independent from `retryable_read`. Never map a transient read error, unavailable selector, disconnected tab, or model error into a fresh Send. `start()` on the same run or an already reserved request ID is rejected. Concurrent operations on one run are rejected with `BUSY`; the caller must also avoid unrelated concurrent mutations of its tab.
