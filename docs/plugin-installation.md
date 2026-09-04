# GPT Pro Plugin installation

Repository marketplace에는 `gptpro` Plugin 하나만 있습니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add gptpro@codex-skills
```

또는 `$skill-installer`로 standalone Skill을 설치할 수 있습니다.

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

별도 MCP Plugin, ChatGPT custom App, Developer Mode, Tunnel profile, Tunnel API key는 필요하지 않습니다. Node 22+, Python 3.11+, macOS ChatGPT 앱은 로컬 요구사항입니다.

Plugin mirror는 `gptpro/`와 byte-identical해야 합니다. Maintainer는 `python3 scripts/sync_skill_mirrors.py --write --package gptpro`로 동기화합니다.
