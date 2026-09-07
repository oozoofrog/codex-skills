# Work model and reasoning selection

Read before every Work submission. Automatic model and effort selection is the default; a separate request to apply the settings is not required. The [official model guide](https://learn.chatgpt.com/docs/models), checked 2026-09-07, documents the model/reasoning control beneath the ChatGPT Work web composer. Available choices depend on account and rollout; inspect the live picker instead of treating this reference or the Codex model catalog as the user's available Work models.

## Choose a proportionate setting

Use **GPT-6 Astra** (`gpt-6-astra`) for every Work submission by default. Do not choose Luna, Terra, or Sol for easier questions; vary Astra's effort instead. A user's explicit different model or keep-current instruction overrides this default. If Astra is unavailable, report configuration blocked and keep the prompt unsent; never silently substitute another model.

Select effort before submission from question difficulty, giving one short reason. These are skill choices, not a promise of identical UI availability or cost:

| Question difficulty | Astra effort |
| --- | --- |
| Simple fact extraction, formatting, or tightly bounded summary | Light |
| Ordinary explanation, comparison, or a small plan | Medium |
| Substantial review, design, evidence interpretation, or document integration | High |
| Interdependent constraints, unresolved contradictions, difficult debugging | Extra High |
| Selective high-impact final judgment or critical counterexample search | Max, only when depth justifies time/usage |

Use only levels exposed for Astra in the actual picker. If a preferred level is absent, choose the next higher visible non-Ultra level within the user's budget and explain; if none fits, resolve the constraint before Send. Explicit effort requests must not be substituted. Work labels may be localized, such as `높음` for High. Ultra introduces subagents; do not choose it just because a question is difficult. It requires an explicit parallel-work request and actual availability. Do not enable hidden/experimental settings or modify account-wide defaults. Standard is the default speed for a new task; Fast/priority requires explicit authorization.

## Configure the same composer before Send

The current native `create_thread` and `send_message_to_thread` tools accept model/effort overrides only for Codex threads. Their Work route starts a prompt with no atomic configuration control. Therefore the default is **Work UI selection, readback, then UI submission from the same composer**. Do not set a browser picker and assume a later native call inherits it. Do not pass Codex overrides for Work, send slash commands as messages, or treat “use High” in prompt text as configuration.

1. Discover an available supported browser and use the live page to enter **Work**, not Chat or local Codex. For an existing task, verify its actual ID/URL and content; for new work, open a fresh Work composer in the requested project without sending a placeholder. Do not overwrite an existing user draft. Use only observed navigation links or a tool-returned URL for an existing task.
2. Inspect the composer model control. Open its model submenu and explicitly select the chosen model if needed. A family/default Power preset can display a model name without an explicit model selection, so check the model submenu as well as the composer label.
3. Inspect the resulting reasoning control after model selection, since changing the model can reset effort. Select the chosen supported level. Prefer semantic controls; if a slider is exposed, focus and use its documented keyboard interaction, observing the label after changes. Do not assume an index or click position represents High, and do not cross into Ultra as an exploration shortcut.
4. Close the picker and read back the composer summary. If the combined label is incomplete, reopen the picker to verify the exact model and effort separately. Confirm Work and the intended destination remain selected. Send only after both settings match. Already matching settings require verification, not needless mutation.
5. Send the prepared prompt once through that same composer. Native submission is allowed only if a future supported contract verifies configuration for that exact Work run, or the user explicitly opts out with current/default settings. Log the distinction in the final response.

A `$gptwork` execution request includes its normal automatic model/effort configuration; do not ask again whether to apply it. Respect explicit “recommend only” or “keep current settings.” Preserve stated time/cost limits. Do not enable Fast/priority, paid features, experimental controls, or account-wide preferences as part of this flow. Use Standard when selecting a speed for a new task; for an existing task, preserve its observed speed unless the user requests otherwise. Never report unobserved speed as applied.

If browser login is required, let the user complete authentication and resume at the same composer. If an app is blocked by the UI tool, do not use AppleScript, shell automation, or private endpoints to bypass it; try a separately supported browser surface. Missing UI controls or failed readback means **configuration blocked, prompt not submitted**. Keep the prepared prompt and explain the one missing step; do not call native creation to make apparent progress.

## Existing tasks and timing

For a requested existing-task follow-up, configure and verify before sending that follow-up, then verify receipt once. For a task already running from an earlier submission, a picker change does not prove that run changed models. Report it as an observed composer setting for subsequent work; do not stop, restart, regenerate, or resend the active task without an explicit request. The first run of a newly requested task must use the pre-submission gate by default, even when the user did not say “first run.”

Report the chosen combination and reason, observed model and effort, whether a change was applied or matching values reused, delivery state, and any current-run timing limit. Recommendation alone is never evidence of successful configuration. Native acceptance alone is never evidence of settings.

## Observed UI evidence and regression scenarios

On 2026-09-07 the browser showed the existing gptwork review as Work with `GPT-5.6 Sol Light`. Its model submenu exposed Astra, Sol, Terra, Luna, and GPT-5.5; choosing Sol exposed a reasoning slider. Selecting High produced `높음` and the composer summary `GPT-5.6 Sol 높음`. Fast was off. This verifies a real existing-composer setting change, not a fresh task's first-run model or a server-side retroactive change. Native app access was blocked; the supported browser remained available. These observations guide the sequence, not hard-coded selectors or availability guarantees.

Check these behavioral scenarios when editing this skill:

- “Review this skill in Work”: prepare the review, select Astra with High for substantive review, configure and verify before Send; do not take the local-edit exemption or native-first path.
- No model request: select Astra and difficulty-based effort; never stop at a recommendation.
- “Use Astra High”: treat both as first-run requirements without an extra timing question.
- Already matching model/effort: read back and proceed without toggling.
- Model choice resets effort: set effort afterward and verify both values.
- UI blocked, login pending, or unavailable exact model: retain the prompt, no default native submission.
- Uncertain Send: inspect the same task; never create a second task to retry configuration.
- Existing active task: a settings change does not authorize interrupting/replaying its request.
- Explicit recommendation-only or keep-current request: honor it and label any unverified settings honestly.
