---
name: unreal-agent
description: Run the local Unreal Agent CLI for a task when the user explicitly asks to use Unreal Agent, then review its results in Codex. Do not use for Unreal Engine work merely because it says Unreal.
---

# Unreal Agent

Unreal Agent is a separate runner, not a Codex execution mode. Codex owns this conversation and invokes the CLI for the requested bounded task. Do not route ordinary coding requests through it unless the user asks.

1. Resolve the intended local workspace from the current task. Confirm `unreal-agent-runner` is available; on this Mac it was installed at `/Users/oozoofrog/.local/bin/unreal-agent-runner`. If unavailable in another environment, explain the limitation instead of silently substituting Codex. Use `unreal-agent-runner -h` to check current options when needed.
2. Read the workspace's applicable instructions and Git status before giving the runner a task. Preserve unrelated or existing changes. Choose an isolated checkout when the requested experiment or dirty-tree ownership makes one necessary; do not assume a new worktree includes uncommitted files.
3. Pass the user's actual task and constraints, an explicit absolute `-workspace`, and both `model` and `thinking_level` selected as below. Prefer a JSON request (stdin or a safely written file) when supplying these fields or `session_id`; do not interpolate untrusted prompt text into a shell command.
4. Capture the runner's JSONL events and exit status. A run handles one request and exits. To continue its persisted work, reuse its `session_id` and session directory in a later run; this does not make the runner a persistent Codex chat. Do not paste secrets or entire logs into the final answer.
5. Inspect the resulting workspace changes and the runner's final outcome yourself. Report what Unreal Agent did, what Codex verified, failures, and remaining work separately. Do not claim a build, runtime check, or test occurred unless its evidence is present. Follow the user's authorization and the workspace's own rules for commits, pushes, and other external effects.

## Runner model and thinking level

Choose both fields for each new runner task. These fields control the Codex model used by the external runner; a skill cannot change the model or reasoning effort of this Codex conversation.

- Preserve each field the user specified. If only one was specified, select the other. If an explicit choice is unavailable or incompatible, report it before running instead of silently substituting another value.
- For `openai-codex` (`UNREAL_HARNESS_LLM_PROVIDER=openai-codex`), choose the smallest currently available pair suited to the task: `gpt-6-luna` / `low` for mechanical, narrow work with an obvious check; `gpt-6-sol` / `medium` for ordinary implementation, debugging, or review; `gpt-6-astra` / `high` for broad changes, uncertain root causes, or consequential decisions. Increase the thinking level within the chosen model for demonstrated complexity (`high` for Sol, `xhigh` or `max` for Astra); do not choose a larger model or level merely because the skill was invoked. These are selection examples, not guaranteed provider defaults or a fixed model catalog.
- Check the runner's current schema and the selected provider's available models and supported levels. If availability cannot be queried, treat the pair as unverified until the runner accepts it. If an automatic choice is rejected, inspect the workspace before selecting another supported pair. For a non-Codex provider, use its own model IDs rather than these examples. A past `openai-codex` smoke run succeeded with `gpt-6-astra`, but that does not establish current availability.
- When resuming a session, keep its previous model and thinking level unless the task or evidence warrants a change. Report the selected pair and any automatic fallback with the runner outcome.
