# Plugin installation

Repository marketplace에는 `gptpro`, `swift-intelligence`, `astra-orchestrator` Plugin이 있습니다. 필요한 Plugin만 선택해 설치합니다. 아래 명령은 해당 버전이 원격 marketplace에 반영된 뒤 사용합니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add gptpro@codex-skills
codex plugin add swift-intelligence@codex-skills
codex plugin add astra-orchestrator@codex-skills
```

이미 등록한 marketplace는 `codex plugin marketplace upgrade codex-skills`로 최신 snapshot을 받은 뒤 필요한 Plugin을 설치합니다.

Astra Orchestrator는 모델·추론 수준을 지정할 수 있는 Codex 서브에이전트 환경이 필요합니다. 리더 설정은 `gpt-6-astra` / `xhigh`이며 스킬 자체가 실행 중인 설정을 바꾸지는 않습니다. 별도 MCP 서버나 설치 hook은 없습니다. 새 작업에서 `$astra-orchestrator:astra-orchestrator`로 호출합니다. 기존 사용자 로컬 `astra-orchestrator`와 함께 설치하면 중복 표시될 수 있습니다. 자세한 내용은 [Astra Orchestrator 설치와 사용](../plugins/astra-orchestrator/README.md)을 참고하세요.

Swift Intelligence는 macOS, Command Line Tools를 포함한 Xcode, Python 3가 필요합니다. Xcode에 포함된 `sourcekit-lsp`를 실행하며 외부 MCP 바이너리나 Python 패키지를 설치하지 않습니다. Swift Intelligence 설치 후 Codex를 다시 시작하고 새 작업을 열어 Skill과 MCP 도구를 로드하십시오. 자세한 내용은 [Swift Intelligence 설치 및 사용](../plugins/swift-intelligence/docs/installation-and-usage.md)을 참고하세요.

`gptpro`는 `$skill-installer`로 standalone Skill을 설치할 수도 있습니다.

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

`gptpro`에는 별도 MCP Plugin, ChatGPT custom App, Developer Mode, Tunnel profile, Tunnel API key는 필요하지 않습니다. Node 22+, Python 3.11+, macOS ChatGPT 앱은 로컬 요구사항입니다.

Plugin mirror는 `gptpro/`와 byte-identical해야 합니다. Maintainer는 `python3 scripts/sync_skill_mirrors.py --write --package gptpro`로 동기화합니다.
