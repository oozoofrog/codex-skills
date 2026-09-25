---
name: unreal-agent
description: Run the local Unreal Agent CLI for a task when the user explicitly asks to use Unreal Agent, then review its results in Codex. Do not use for Unreal Engine work merely because it says Unreal.
---

# Unreal Agent

Unreal Agent is a separate runner, not a Codex execution mode. Codex owns this conversation and invokes the CLI for the requested bounded task. Do not route ordinary coding requests through it unless the user asks.

1. Resolve the intended local workspace from the current task. Confirm `unreal-agent-runner` is available; on the reference Mac it was installed at `/Users/oozoofrog/.local/bin/unreal-agent-runner`. This is a historical discovery hint, not a portable default. If unavailable, explain the limitation instead of silently substituting Codex. Use `unreal-agent-runner -h` to check current options when needed.
2. Read the workspace's applicable instructions and Git status before giving the runner a task. Preserve unrelated or existing changes. Choose an isolated checkout when the requested experiment or dirty-tree ownership makes one necessary; do not assume a new worktree includes uncommitted files.
3. Pass the user's actual task and constraints, an explicit absolute `-workspace`, and both `model` and `thinking_level` selected as below. Prefer a JSON request (stdin or a safely written file) when supplying these fields or `session_id`; do not interpolate untrusted prompt text into a shell command.
4. Capture the runner's JSONL events and exit status. A run handles one request and exits. To continue its persisted work, reuse its `session_id` and session directory in a later run; this does not make the runner a persistent Codex chat. Do not paste secrets or entire logs into the final answer.
5. Inspect the resulting workspace changes and the runner's final outcome yourself. Report what Unreal Agent did, what Codex verified, failures, and remaining work separately. Do not claim a build, runtime check, or test occurred unless its evidence is present. Follow the user's authorization and the workspace's own rules for commits, pushes, and other external effects.

## Runner model and thinking level

Choose both fields for each new runner task. These fields control the Codex model used by the external runner; a skill cannot change the model or reasoning effort of this Codex conversation.

- Preserve each field the user specified. If only one was specified, select the other. If an explicit choice is unavailable or incompatible, report it before running instead of silently substituting another value.
- For `openai-codex` (`UNREAL_HARNESS_LLM_PROVIDER=openai-codex`), start with an adequate currently available pair: `gpt-6-luna` / `high` for mechanical, narrow work with an obvious check; `gpt-6-sol` / `medium` for ordinary implementation, debugging, or review; `gpt-6-astra` / `high` for broad changes, uncertain root causes, or consequential decisions. Increase effort within the chosen model for demonstrated complexity (`high` for Sol, `xhigh` or `max` for Astra); do not choose a larger model or level merely because the skill was invoked. These are policy candidates, not guaranteed provider defaults or a fixed catalog.
- Check the runner's current schema and the selected provider's available models and supported levels. If availability cannot be queried, treat the pair as unverified until accepted, and distinguish acceptance from observed execution settings. Inspect any provider/custom-agent setting override exposed by the actual runner. Do not assume Codex CLI precedence is implemented identically by this runner.
- If an automatic choice is rejected, inspect the workspace before selecting another supported pair. For a non-Codex provider, use its own IDs only when that provider was explicitly requested or already authorized; this skill does not authorize a provider switch. A past `openai-codex` smoke run succeeded with `gpt-6-astra`, but that does not establish current availability.
- When resuming a session, keep its previous model and thinking level unless the task or evidence warrants a change. Report desired, submitted and observed settings separately; unavailable observations are `unverified`. Report automatic alternatives and their reasons. Never change the calling Codex model, context-window settings, login or permissions to repair runner compatibility.

## Luna effort evidence

The prior `low` example was a narrow-task policy, not a measured speed/quality guarantee. This revision uses `high` as the conservative automatic starting point, informed by [OpenAI subagent guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents) checked 2026-09-25. That guidance is not proof that this external runner supports the pair. An explicit supported `low` request remains binding.

Use `low` as an automatic policy only after an explicitly authorized comparison establishes the relevant task class: same initial files and acceptance checks, separate fresh sessions/workspaces, observed settings, full completion quality, retries, Codex repair time and total usage. Keep unknown costs unknown. Record failed and blocked attempts; do not repeatedly rerun until a cheaper-looking sample appears. This skill update does not launch the experiment or claim it passed.

Do not invoke this runner as an automatic fallback for unavailable Codex subagents, Chat/Work consultation or Jev decisions. Its explicit invocation and external-effect boundaries remain unchanged.
