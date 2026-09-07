# Model and reasoning selection

Read before each new submission or requested follow-up in either Chat or Work. Choose an adequate combination for the actual prompt, then apply it using [composer settings](composer-settings.md). A recommendation or model name in prompt text does not configure a run.

## Decision order

1. Preserve the requested surface/conversation and any explicit model, reasoning, speed, deadline, or spending limit. Fill only unspecified settings automatically. “Chat Pro” fixes Chat and Pro but leaves the model open; “Chat Astra Pro” fixes all three. “Keep current” preserves the observed settings. “Recommend only” does not change settings or send.
2. Identify the deliverable and difficulty: bounded extraction/transformation, ordinary explanation or tool work, open-ended analysis/review, or a sustained workflow across dependent steps. Consider ambiguity, conflicting constraints, source integration, verification difficulty, and consequences of error. Prompt length alone is not complexity; a short high-impact decision may need more depth than a long formatting request.
3. Inspect models in the actual surface, then choose an appropriate candidate below. Inspect that model's reasoning options before selecting effort. Chat, Work, Codex, and API catalogs are not interchangeable. Use current official guidance when an unfamiliar model requires a capability comparison.
4. Choose sufficient depth within the user's constraints. Give a short reason before submission, such as “Work · Luna · Light: fixed-schema extraction with a local result check.” Report the later UI readback separately. A higher effort does not make different model families equivalent.

## Starting combinations

These are this skill's defaults, informed by the [official model guide](https://learn.chatgpt.com/docs/models) checked 2026-09-07. They are decision aids, not measured quality/cost guarantees or a fixed availability list.

| Purpose and complexity | Starting candidate when available |
| --- | --- |
| Clear extraction, classification, formatting, or structured summary with an easy result check | GPT-5.6 Luna · Light |
| Everyday explanation, comparison, small implementation, or ordinary tool work with clear scope | GPT-5.6 Terra · Medium |
| Substantial review, ambiguous analysis, design tradeoffs, or polished synthesis | GPT-5.6 Sol · High |
| Difficult end-to-end work across dependent code, tools, sources, and checks | GPT-6 Astra · High; Extra High for intertwined constraints or unresolved contradictions |

Model and effort are separate choices. For example, a routine Terra task may only need Light; a bounded Sol explanation may need Medium; a simple follow-up to an explicitly requested Astra model can use Light. Do not raise both automatically for every review or choose the smallest model solely to reduce usage when the consequences of error require stronger judgment.

Use the selected model's actual effort controls:

- **Light/Low:** bounded work with little planning or uncertainty.
- **Medium:** ordinary planning and several straightforward steps.
- **High:** substantial interpretation, checking, or tradeoffs.
- **Extra High:** intertwined constraints, difficult debugging, or unresolved contradictions.
- **Max, or Chat Pro where available:** selective high-impact final judgment or difficult counterexample search when the expected benefit justifies added time/usage. These are different surface-specific settings, not equivalent levels. Pro is mandatory when explicitly requested; an ordinary Chat request does not require it.
- **Ultra:** do not select automatically. Use only with explicit parallel-work authorization and live support; it can involve subagents. Complexity alone does not grant that permission.

## Availability and limits

For automatic choice, use available candidates suitable for the same purpose and requested surface. If Chat lacks Luna/Terra, a visible Sol with an appropriate lighter effort can handle a bounded task. If Astra is absent, an automatically selected Sol may be adequate for analysis; reassess whether the task's tools and difficulty still fit. Explain the selected alternative before Send. Do not switch Chat to Work, claim an unverified “Latest” model, or silently relax a hard limit.

An **explicit** model or effort is binding. If it is absent or the pair is unsupported, preserve the prepared request unsent and report the exact missing combination. If an automatic preferred effort is absent, choose an adequate visible level within constraints; do not blindly round upward. If no combination satisfies the task and hard constraints, resolve that conflict before sending. Unobserved pricing or latency cannot prove compliance with an exact numerical cap.

Standard is the default speed for new work; Fast/priority requires an explicit request. Preserve observed speed for an existing conversation unless asked to change it. Do not enable paid tools, experimental settings, account-wide defaults, or hidden controls. A request for the fastest model or a short deadline alone does not authorize Fast pricing. Do not claim a speed setting that was not observed.

Reassess only at a requested follow-up or when preparing work not yet sent. An inadequate answer is grounds for a local check and a clear limitation, not permission to resend at greater effort, start an ensemble, regenerate, or purchase more usage. Changing a picker during an active run only establishes settings for a later submission.

## Behavioral checks when this policy changes

Check automatic bounded work and a substantially different analysis/workflow request; confirm purpose changes the choice when live options allow it. Also check partial explicit settings, unavailable exact combinations, keep-current, and hard budget conflicts without unnecessary messages. Confirm model changes followed by effort readback, preserved surface, no duplicate send, and full response return. Separate policy decisions, observed UI configuration, and actual response/attachment evidence.
