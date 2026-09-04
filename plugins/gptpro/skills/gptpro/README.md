# gptpro 0.6

`gptpro` lets Codex send one selected, secret-scanned code snapshot to the logged-in ChatGPT Pro in the macOS ChatGPT app and collect its answer automatically.

```text
$gptpro
  -> select files and scan secrets
  -> build exact outbound.md (maximum 256 KiB)
  -> exact or bounded standing approval
  -> loopback Electron delivery to exact gpt-5-6-pro in normal Chat
  -> one POST and exact authenticated response readback
  -> independent Codex validation
```

ChatGPT receives only the text inside `outbound.md`. It receives no live filesystem, shell, write, build, test, Git, MCP, Browser, or server-tool access. After the single POST, authenticated conversation GETs poll for the deterministic message ID and verify the exact outbound bytes, tool-free final status, and response body. This avoids unstable ChatGPT DOM selectors. `collect-response` remains a GET-only recovery command for process interruption or automatic collection failure.

## Requirements

- macOS and `/Applications/ChatGPT.app`
- a logged-in ChatGPT Pro session
- Node.js 22 or newer; no npm install
- Python 3.11 or newer

## Start

```bash
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
python3 <skill-dir>/scripts/gptpro.py launcher-install --json
python3 <skill-dir>/scripts/gptpro.py desktop-doctor --json
```

`launcher-install` adds the small user-only app `~/Applications/gptpro Launcher.app`. It starts a second `/Applications/ChatGPT.app` process with the dedicated owner-only profile `~/Library/Application Support/gptpro/runner/v1/profile` and loopback port 9223. The ordinary ChatGPT app can remain open and does not need to be relaunched. The launcher does not copy or modify ChatGPT, extract credentials, stop either app, add a Login Item, or remain resident.

When the consultation session is over, close only the dedicated Runner window if desired. `launcher-status` reports `stopped`, `runner_starting`, `runner_unverified`, `runner_verified`, `port_conflict`, or `process_state_unknown`; only `desktop-doctor` is authoritative. An explicit non-default `--endpoint` remains a development diagnostic and is not the normal Skill path.

Then invoke:

```text
$gptpro review 모드로 src와 tests의 현재 변경을 ChatGPT Pro와 함께 검토해주세요.
```

See the [user manual](references/user-manual.md), [workflow](references/workflow.md), and [security boundary](references/security.md). The Electron bridge is a private, best-effort compatibility layer and can break after a ChatGPT app update.
