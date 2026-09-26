# Model and reasoning selection

Read before each new submission or requested follow-up in either Chat or Work. Choose an adequate combination for the actual prompt, then apply it using [composer settings](composer-settings.md). A recommendation or model name in prompt text does not configure a run.

## Decision order

1. Preserve the requested surface/conversation and any explicit model, reasoning, speed, deadline, or spending limit. Fill only unspecified settings automatically. “Chat Pro” fixes Chat and Pro but leaves the model open; “Chat Astra Pro” fixes all three. “Keep current” preserves the observed settings. “Recommend only” does not change settings or send.
2. Identify the deliverable and difficulty: bounded extraction/transformation, ordinary explanation or tool work, open-ended analysis/review, or a sustained workflow across dependent steps. Consider ambiguity, conflicting constraints, source integration, verification difficulty, and consequences of error. Prompt length alone is not complexity; a short high-impact decision may need more depth than a long formatting request.
3. Inspect models in the actual surface. Chat, Work, Codex, and API catalogs are not interchangeable. Choose a candidate below only when that exact surface exposes it. Inspect its effort options; do not derive an API ID or rename a UI label by replacing a version number.
4. Choose sufficient depth within the user's constraints. State the surface, exact observed model/effort labels and a short task-based reason before submission. Report the later UI readback separately. A higher effort does not make model families equivalent.

## Surface-specific starting candidates

Policy reviewed 2026-09-25 against the [official model guide](https://learn.chatgpt.com/docs/models) and [subagent guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents). At that date the guide lists GPT-6 Luna/Sol in Work and Codex, not Chat, with GPT-5.6 options remaining during rollout. This is dated guidance, not an entitlement list or a permanent ban on future Chat models. Live options and explicit user constraints remain authoritative. Official Codex effort recommendations inform the Work starting candidates below; a CLI effort name does not prove the UI supports an equivalent control.

| Purpose | Work candidate, when visible | Chat candidate, when visible |
| --- | --- | --- |
| Clear extraction, formatting, or a repeatable transformation with an easy check | GPT-6 Luna · High | GPT-5.6 Luna · Light; otherwise a suitable visible Chat model |
| Ordinary implementation, explanation, comparison, or tool work with clear scope | GPT-6 Sol · Medium | GPT-5.6 Terra · Medium or a suitable visible GPT-5.6 Sol level |
| Substantial review, uncertain analysis, or design tradeoffs | GPT-6 Sol · High | GPT-5.6 Sol · High |
| Difficult dependent work with consequential constraints | GPT-6 Astra · High / Extra High | GPT-6 Astra only when actually visible; otherwise reassess a suitable visible Chat model |

These are skill defaults, not measured quality/cost guarantees. In Work, a suitable visible GPT-5.6 candidate may be used when the preferred automatic GPT-6 choice is unavailable. Do not switch surfaces to obtain it. In Chat, do not request GPT-6 Luna/Sol merely because Work or Codex exposes them. Newly visible models require a fresh capability check, not a blind table substitution. An unavailable **explicit** model remains unsent even when an automatic alternative would have been acceptable.

Model and effort are separate choices. A simple follow-up to an explicitly requested Astra can use a lighter supported effort when effort was not specified. Do not raise both automatically for every review or choose the smallest model solely to reduce usage when the consequences of error require stronger judgment.

Use the selected model's actual effort controls:

- **Light/Low:** bounded work with little planning or uncertainty; use deliberately rather than mapping all Luna tasks here.
- **Medium:** ordinary planning and several straightforward steps.
- **High:** substantial interpretation, checking, or tradeoffs; also the initial GPT-6 Luna candidate above.
- **Extra High:** intertwined constraints, difficult debugging, or unresolved contradictions.
- **Max, or Chat Pro where available:** selective high-impact final judgment or difficult counterexample search when justified. These are distinct surface-specific settings, not equivalent levels. Pro is mandatory when explicitly requested.
- **Ultra:** never select automatically. It requires explicit parallel-work authorization and live support; complexity alone does not grant permission.

## Availability and limits

For automatic choice, use adequate available candidates in the same requested surface. Explain a changed automatic candidate before Send. If an automatic preferred effort is absent, choose an adequate visible level within constraints; do not blindly round upward. Do not claim an unverified “Latest” model or silently relax a hard limit.

An explicit model or effort is binding. If absent or incompatible, preserve the prepared request unsent and report the exact missing combination. Do not treat “Chat Pro” as an account badge or Work Max/Ultra. Resolve unsatisfied hard limits before sending. Unobserved pricing or latency cannot establish compliance with an exact numerical cap.

Standard is the default speed for new work; Fast/priority requires an explicit request. Preserve observed speed for an existing conversation unless asked to change it. Do not enable paid tools, experimental settings, account-wide defaults, or hidden controls. A deadline or a request for the fastest model alone does not authorize Fast pricing. Do not claim a speed setting that was not observed.

Reassess only at a requested follow-up or when preparing work not yet sent. An inadequate answer calls for a local check and a clear limitation, not automatic resending, an ensemble, regeneration, or purchased usage. Changing a picker during an active run establishes only later-submission settings. On uncertain Send, follow [transport recovery](transport-recovery.md), not this selection procedure.

## Behavioral checks when this policy changes

Check a bounded Work request and a different analysis request with actual live options. Also check Chat with an unavailable explicitly requested Work model, partial explicit settings, keep-current, recommend-only, Pro-vs-Max, and hard budget conflicts. Confirm model changes followed by effort readback, preserved surface, no duplicate Send, and full response return. Record policy decisions, observed UI configuration, and response/attachment evidence separately. Static scenario checks are not a live UI test.
