# Plugin installation

Repository marketplace에는 `gptplease`, `swift-intelligence`, `astra-orchestrator`가 있습니다. 필요한 Plugin만 선택합니다. 아래 명령은 해당 변경이 원격에 반영된 뒤 사용합니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add gptplease@codex-skills
codex plugin add swift-intelligence@codex-skills
codex plugin add astra-orchestrator@codex-skills
```

이미 등록한 원격 marketplace는 `codex plugin marketplace upgrade codex-skills`로 snapshot을 갱신한 뒤 설치합니다. 로컬 checkout marketplace를 사용하는 경우에는 그 source를 확인한 뒤 같은 이름으로 재설치합니다.

`gptplease`는 지원되는 브라우저 제어와 ChatGPT 로그인이 필요합니다. Chat·Work에서 목적·복잡도에 맞는 모델과 사고 수준을 선택하고 명시 설정을 지키며 전송 전에 확인한 뒤, 실제 파일 첨부와 완료 응답 회수를 같은 호출 세션에서 수행합니다. 설치 후 새 대화에서 `$gptplease` 또는 `$gptplease:gptplease`를 호출합니다. [사용 안내](../gptplease/README.md)를 참고하세요.

설치 성공, 새 로더 노출, 실제 새 작업이 읽은 경로를 구분해 확인합니다. 2026-09-07에는 새 작업의 스킬 목록이 삭제된 이전 캐시 경로를 가리켜 같은 패키지의 현재 설치 경로를 찾아 읽어야 했습니다. 이 경우 실제 manifest·스킬 버전을 대조하고 경로 불일치를 보고하며, 이전 목록만으로 최신본 자동 로드를 성공 처리하지 않습니다. 계속 낡은 경로가 노출되면 Codex를 다시 열고 새 작업에서 확인합니다.

이전 이름을 설치했다면 CLI로 제거해 설정과 캐시까지 정리합니다. marketplace 항목을 지운 것만으로 설치 캐시가 제거되지는 않으며, 앱이 미설치로 표시해도 새 로더에서 노출 여부를 확인해야 합니다.

```bash
codex plugin remove gptwork@codex-skills
codex plugin remove gptpro@codex-skills
```

별도 standalone 스킬은 설치 폴더에서 제거해 중복 노출을 피합니다. 과거 `.gptpro` 상담 패키지와 Runner 로그인 프로필은 삭제·이관하지 않습니다. 전용 Launcher는 더 이상 필요하지 않습니다.

Standalone이 필요하면 `gptplease/`를 skill-installer로 선택 설치합니다. 제거한 `manage_skills.py`는 사용하지 않습니다.

Astra Orchestrator는 모델·추론 수준을 지정할 수 있는 Codex 서브에이전트 환경이 필요합니다. 리더 설정은 `gpt-6-astra` / `xhigh`이며 스킬 자체가 실행 중인 설정을 바꾸지는 않습니다. 별도 MCP 서버나 설치 hook은 없습니다. 새 작업에서 `$astra-orchestrator:astra-orchestrator`로 호출합니다. 기존 사용자 로컬 `astra-orchestrator`와 함께 설치하면 중복 표시될 수 있습니다. 자세한 내용은 [Astra Orchestrator 설치와 사용](../plugins/astra-orchestrator/README.md)을 참고하세요.

Swift Intelligence는 macOS, Command Line Tools를 포함한 Xcode, Python 3가 필요합니다. Xcode에 포함된 `sourcekit-lsp`를 실행하며 외부 MCP 바이너리나 Python 패키지를 설치하지 않습니다. Swift Intelligence 설치 후 Codex를 다시 시작하고 새 작업을 열어 Skill과 MCP 도구를 로드하십시오. 자세한 내용은 [Swift Intelligence 설치 및 사용](../plugins/swift-intelligence/docs/installation-and-usage.md)을 참고하세요.
