---
name: unreal-agent
description: Run the local Unreal Agent CLI for a task when the user explicitly asks to use Unreal Agent, then review its results in Codex. Do not use for Unreal Engine work merely because it says Unreal.
---

# Unreal Agent

Unreal Agent is a separate runner, not a Codex execution mode. Codex owns this conversation and invokes the CLI for the requested bounded task. Do not route ordinary coding requests through it unless the user asks.

1. Resolve the intended local workspace from the current task. Confirm `unreal-agent-runner` is available; on this Mac it was installed at `/Users/oozoofrog/.local/bin/unreal-agent-runner`. If unavailable in another environment, explain the limitation instead of silently substituting Codex. Use `unreal-agent-runner -h` to check current options when needed.
2. Read the workspace's applicable instructions and Git status before giving the runner a task. Preserve unrelated or existing changes. Choose an isolated checkout when the requested experiment or dirty-tree ownership makes one necessary; do not assume a new worktree includes uncommitted files.
3. Pass the user's actual task and constraints, an explicit absolute `-workspace`, and a model. Preserve any user-selected model and thinking level. For the installed `openai-codex` provider, `UNREAL_HARNESS_LLM_PROVIDER=openai-codex` with `model: "gpt-6-astra"` worked in a prior smoke run; check current availability rather than treating that as a universal default. Prefer a JSON request (stdin or a safely written file) when supplying `session_id`, `model`, or `thinking_level`; do not interpolate untrusted prompt text into a shell command.
4. Capture the runner's JSONL events and exit status. A run handles one request and exits. To continue its persisted work, reuse its `session_id` and session directory in a later run; this does not make the runner a persistent Codex chat. Do not paste secrets or entire logs into the final answer.
5. Inspect the resulting workspace changes and the runner's final outcome yourself. Report what Unreal Agent did, what Codex verified, failures, and remaining work separately. Do not claim a build, runtime check, or test occurred unless its evidence is present. Follow the user's authorization and the workspace's own rules for commits, pushes, and other external effects.
