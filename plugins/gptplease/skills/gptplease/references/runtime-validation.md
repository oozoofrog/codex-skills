# Bundled transport validation

This document records evidence for the 0.2.0 implementation of issue #45. General contract tests and account-bound browser results are different evidence. The old 2026-09-07 manual skill checks are not used as proof that this new runtime worked.

## Automated checks

Run from the repository root:

```sh
node --test gptplease/tests/*.test.mjs
python3 -m unittest discover -s scripts/tests -v
python3 scripts/sync_skill_mirrors.py --package gptplease
```

Node tests cover exact Chat/Work configuration, unsupported settings before Send, pending uploads and configuration drift, ambiguous Send/read recovery with one submission, old and duplicate turn identity, temporary response placeholders, stable completion, truncation, code-operator/indentation loss in copied text, actual attachment manifests including unexpected attachments on a zero-file request, cancellation and checkpoint restoration, reservation of restored request IDs, concurrent operation rejection, bounded read failures, and generated artifact link metadata. Advice remains data; no local tools or callbacks execute it.

An independent evaluator exercised production adapter methods with additional fixtures. Its findings about zero-file preflight, lost operators, and restored request IDs became regression tests. These tests do not prove authentication, current menu availability, server-internal model routing, actual uploads, or live response retrieval.

## Authenticated browser evidence — 2026-09-12, Korean UI

Only synthetic prompts and the bundled test fixtures were used for intentional submissions. The modules were imported directly into the supported CUA JavaScript session, with no separate browser profile or server. Model names below are observed UI selections, not claims about server-internal model IDs.

| Scenario | Observed evidence |
| --- | --- |
| New Chat | GPT-5.6 Sol + `중간`; real conversation and user/assistant IDs; complete `CHAT-SMOKE-45` returned. |
| Existing Chat follow-up | Same original Chat URL; Sol + `중간`; the new user and final assistant were correlated separately from the earlier probe; `Chat transport confirmed.` returned. |
| Unsupported exact request | Chat + GPT-6 Astra + Pro failed with `MODEL_UNAVAILABLE`; URL stayed on the fresh composer, text remained empty, Send was not attempted. |
| New Work + three general files | GPT-5.6 Luna + `중간`; chooser uploaded `probe.json`, `probe.md`, `probe.swift`; all three received attachment cards matched; the answer returned `7`, `ORBIT-45`, `11`, matching their actual contents. |
| Existing Work follow-up | Same Work URL and settings; a new user/assistant pair was observed without confusing the earlier attachment review. |
| Cancellation after Send | The Work follow-up was cancelled locally after confirmed delivery; its checkpoint resumed read-only into the same user/assistant pair, without another Send. ChatGPT generation was not stopped. |
| Long final response | Copy returned 80 numbered lines through `LINE 080` and `END-WORK-LONG-45`, exceeding 7,300 characters. |
| Generated artifact | Work created `transport-artifact.txt`; the runtime retains the actual file button identity/name and its conversation-scoped `sandbox:` link. Artifact bytes remain separately classified. |
| Ambiguous delivery | Actual first reads of new conversations could precede URL/message availability and remained `delivery_unknown`; subsequent reads recovered the same submission. Lost-Send exceptions and duplicate prevention are additionally exercised by deterministic fixtures. |

During development, live checks caught paragraph newline expansion, temporary assistant placeholders, hidden upload-input behavior, different attachment-card markup, and empty clipboard restoration. Pre-Send failures remained unsent; reads after an attempted Send used the original conversation. Current code and instructions incorporate those observations.

## Scope and limits

- Supported live checks used the current Korean Chat/Work UI. English label candidates exist for common controls, but an English-account E2E was not run. Unknown controls/signatures stop the transport.
- Reuploading a filename can make ChatGPT append `(1)` or another suffix. The exact-filename contract then fails before Send. Use explicitly prepared, authorized copies with unique filenames if necessary; the transport does not silently map renamed cards to source files.
- Three very small files (JSON, Markdown, Swift) were tested together. This does not establish all extensions, large-file limits, upload size ceilings, or byte-for-byte round-trip integrity. No general size limit is invented here.
- Artifact references and final Markdown are distinct from downloaded bytes. The transport does not automatically download all files/images or follow every citation. A caller that needs artifact contents must inspect them through supported tools.
- Browser login and supported CUA control must already be available. Installing the package alone does not provide them. No cookies/session tokens are read or stored.
- State is held in the invoking session. There is no durable globally shared submission ledger, daemon, or exactly-once guarantee across lost state. A checkpoint enables read-only continuation; it is not a signed receipt or authority to resend.
- Interactive Work approval/input flows and every possible error UI are not exhaustively account-tested. An unfamiliar blocked UI requires caller inspection; ordinary questions in the final answer still need the caller's judgment.
- Packaging checks verify source/mirror content and no MCP/apps manifest. Installation/enabled state and fresh-loader exposure must be recorded separately when checking a particular machine; they are not implied by these browser results.
