# Plugin installation

Repository marketplace에는 `gptplease`, `swift-intelligence`, `astra-team-building`, `figma-computer-use`, `session-continuity`, `ponytail-beck-tdd`, `unreal-agent`, `local-ai-studio`가 있습니다. 필요한 Plugin만 선택합니다. 아래 명령은 해당 변경이 원격에 반영된 뒤 사용합니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add gptplease@codex-skills
codex plugin add swift-intelligence@codex-skills
codex plugin add astra-team-building@codex-skills
codex plugin add figma-computer-use@codex-skills
codex plugin add session-continuity@codex-skills
codex plugin add ponytail-beck-tdd@codex-skills
codex plugin add unreal-agent@codex-skills
codex plugin add local-ai-studio@codex-skills
```

이미 등록한 원격 marketplace는 `codex plugin marketplace upgrade codex-skills`로 snapshot을 갱신한 뒤 설치합니다. 로컬 checkout marketplace를 사용하는 경우에는 그 source를 확인한 뒤 같은 이름으로 재설치합니다.

`ponytail-beck-tdd`는 켄트 벡의 TDD·Tidy First 글과 Ponytail의 구현 원칙을 담은 명시적 호출용 스킬입니다. 설치 후 새 작업에서 `$ponytail-beck-tdd` 또는 `$ponytail-beck-tdd:ponytail-beck-tdd`로 호출합니다. 필요한 원칙을 자체 포함하므로 별도 Ponytail 설치나 MCP 서버가 필요하지 않습니다. 개인 지시를 수정하거나 일반 코딩에 자동 적용하지 않으며, 작은 테스트의 의무 삭제 규칙도 없습니다. [스킬 본문](../ponytail-beck-tdd/SKILL.md)과 [원문 근거](../ponytail-beck-tdd/references/kent-beck.md)를 참고하세요. Standalone 설치를 선택할 때는 `ponytail-beck-tdd/`를 skill-installer로 설치하고 Plugin과 중복 설치하지 않습니다. 기존 구현·테스트의 점검과 개선을 모두 지원하며, 점검만 요청하면 파일 변경 없이 보고합니다. 개선 시에는 [기존 테스트 개선 절차](../ponytail-beck-tdd/references/existing-tests.md)에 따라 전후 효과를 확인합니다.

`gptplease`는 지원되는 CUA 브라우저 제어와 ChatGPT 로그인이 필요합니다. Plugin과 standalone 모두 `runtime/` 모듈을 포함하며 해당 브라우저 JavaScript 세션에서 직접 import합니다. 추가 MCP 서버·실행기·npm 의존성은 없고, 자동 테스트만 Node.js 20 이상에서 실행합니다. [실행 계약](../gptplease/references/transport-contract.md)을 참고하세요. Chat·Work에서 목적·복잡도에 맞는 모델과 사고 수준을 선택하고 명시 설정을 지키며 전송 전에 확인한 뒤, 실제 파일 첨부와 완료 응답 회수를 같은 호출 세션에서 수행합니다. 설치 후 새 대화에서 `$gptplease` 또는 `$gptplease:gptplease`를 호출합니다. [사용 안내](../gptplease/README.md)를 참고하세요.

설치 성공, 새 로더 노출, 실제 새 작업이 읽은 경로를 구분해 확인합니다. 2026-09-07에는 새 작업의 스킬 목록이 삭제된 이전 캐시 경로를 가리켜 같은 패키지의 현재 설치 경로를 찾아 읽어야 했습니다. 이 경우 실제 manifest·스킬 버전을 대조하고 경로 불일치를 보고하며, 이전 목록만으로 최신본 자동 로드를 성공 처리하지 않습니다. 계속 낡은 경로가 노출되면 Codex를 다시 열고 새 작업에서 확인합니다.

이전 이름을 설치했다면 CLI로 제거해 설정과 캐시까지 정리합니다. marketplace 항목을 지운 것만으로 설치 캐시가 제거되지는 않으며, 앱이 미설치로 표시해도 새 로더에서 노출 여부를 확인해야 합니다.

```bash
codex plugin remove gptwork@codex-skills
codex plugin remove gptpro@codex-skills
```

별도 standalone 스킬은 설치 폴더에서 제거해 중복 노출을 피합니다. 과거 `.gptpro` 상담 패키지와 Runner 로그인 프로필은 삭제·이관하지 않습니다. 전용 Launcher는 더 이상 필요하지 않습니다.

Standalone이 필요하면 `gptplease/`를 skill-installer로 선택 설치합니다. 제거한 `manage_skills.py`는 사용하지 않습니다.

`figma-computer-use`는 Figma MCP 대신 호스트의 `mcp__cua_repl.js` computer-use를 사용합니다. 이 Plugin 자체에는 MCP 서버나 Figma connector가 없으므로 computer-use가 제공되는 환경과 Figma 접근 권한이 필요합니다. 설치 후 새 작업에서 `$figma-computer-use:figma-computer-use`로 호출합니다. [내부 매뉴얼](../figma-computer-use/references/figma-manual.md)과 [호환성·버전 관리](../figma-computer-use/references/maintenance.md)를 포함합니다. 원본 수정은 설치나 현재 작업의 새 스킬 노출을 의미하지 않습니다.

Astra Team Building은 모델·추론 수준을 지정할 수 있는 Codex 서브에이전트 환경에서 역할과 규모를 조절합니다. 현재 리더의 실행 설정을 보존하고 내부 과제는 서브에이전트로 진행합니다. 새 작업에서 `$astra-team-building:astra-team-building`으로 호출합니다. 기존 `astra-orchestrator`를 대체하며 중복 설치를 피합니다. 자세한 내용은 [설치와 사용](../plugins/astra-team-building/README.md)을 참고하세요.

Swift Intelligence는 macOS, Command Line Tools를 포함한 Xcode, Python 3가 필요합니다. Xcode에 포함된 `sourcekit-lsp`를 실행하며 외부 MCP 바이너리나 Python 패키지를 설치하지 않습니다. Swift Intelligence 설치 후 Codex를 다시 시작하고 새 작업을 열어 Skill과 MCP 도구를 로드하십시오. 자세한 내용은 [Swift Intelligence 설치 및 사용](../plugins/swift-intelligence/docs/installation-and-usage.md)을 참고하세요.

`session-continuity`는 일반 Codex 세션의 작업 상태 초기화·재개·checkpoint·완료 정리를 지원합니다. 리더/워커나 MCP 서버가 필요하지 않으며, 선택적 보조 스크립트는 Python 3.9+와 Git을 사용합니다. 설치 후 새 작업에서 `$session-continuity:session-continuity`로 호출합니다. 저장소 초기화는 호출 후 요청 범위에서 수행하고, `.gitignore` 수정은 선택 사항입니다. [설치와 사용 안내](../session-continuity/README.md), [실행한 검증과 한계](../session-continuity/VALIDATION.md)를 참고하세요.

## 모델 정책 업데이트

`gptplease` 0.3.0의 Chat/Work 분리, `unreal-agent` 0.1.3의 실행 설정 관측, `session-continuity` 0.1.1의 단일 복구 지점은 유지합니다. `astra-team-building` 0.1.0은 이전 Astra-only/선택형 mixed-model 정책을 대체하며 작업에 맞는 혼합 배정과 동적 팀 구성을 제공합니다. [모델 역할 분담 문서](model-routing-review.md)와 [기존 검증 기록](model-routing-validation.md)의 과거 실행 범위를 구별하세요.

혼합 모델은 설치만으로 활성화되지 않습니다. 메인 Codex 모델·컨텍스트·provider·인증·권한을 변경하지 않으며 전역 custom agent나 daemon을 설치하지 않습니다. PR 브랜치의 변경은 merge 전 `main` 설치에 포함되지 않습니다. 이미 사용하는 source와 버전을 확인하고 명시한 설치 경로만 갱신하세요. 과거 실행 기록을 새 버전의 live 검증으로 해석하지 않습니다.

## Unreal Agent

`unreal-agent`는 skills-only Plugin `0.1.3`입니다. 설치 후 새 작업에서 `$unreal-agent` 또는 `$unreal-agent:unreal-agent`로 명시적으로 호출합니다. 일반 코딩이나 Unreal Engine 작업이라는 이유만으로 자동 실행하지 않으며 Codex 실행 모드도 아닙니다. Standalone을 원하면 `unreal-agent/`를 skill-installer로 선택 설치하고 Plugin과 중복 설치하지 않습니다. 기존 전역 스킬이 있다면 덮어쓰지 말고 어느 설치본을 사용할지 먼저 확인하세요.

변경이 원격에 반영되기 전에는 위 원격 설치 명령만으로 새 Plugin을 받을 수 없습니다. 로컬에서 시험하려면 이 저장소 루트에서 `codex plugin marketplace add "$PWD"`로 checkout을 등록한 뒤 `codex plugin add unreal-agent@codex-skills`를 사용합니다. 같은 이름의 marketplace가 이미 있으면 먼저 source가 이 checkout인지 확인하세요. 저장소 파일 추가와 실제 설치·활성화·새 세션 노출은 별개입니다.

Go 1.27+, Git, Python 3.9+, Codex CLI가 있는 환경에서는 runner와 Plugin을 한 명령으로 준비할 수 있습니다:

```bash
curl -fsSL https://raw.githubusercontent.com/oozoofrog/codex-skills/main/scripts/install_unreal_agent.sh | bash
```

이 명령은 upstream `v0.2.0`의 고정 commit을 확인해 `~/.local/bin/unreal-agent-runner`에 빌드·설치합니다 (`UNREAL_AGENT_BIN_DIR`로 경로 선택 가능). Go 버전은 upstream `go.mod`의 최소 1.27.0 이상이어야 합니다. 이미 관리 중인 바이너리는 재실행 시 그대로 두고, `bash scripts/install_unreal_agent.sh --reinstall`은 checksum이 맞는 관리본만 교체하며 이전 바이너리와 marker의 보관 위치를 출력합니다. 기존 미관리/변조 바이너리나 symlink는 덮어쓰지 않습니다. PATH에 설치 디렉터리가 없으면 추가하세요. provider 인증은 설치하지 않습니다. curl 파이프라인 실행 전에는 스크립트 소스를 확인하세요.

기본 실행은 `codex plugin marketplace list --json` 및 `codex plugin list --json`으로 먼저 source와 설치/활성화 상태를 검사합니다. marketplace가 없으면 `codex plugin marketplace add oozoofrog/codex-skills --ref main`, 일치하는 원격 등록에서 Plugin을 새로 설치할 때는 upgrade, 검증된 로컬 checkout에서는 등록 변경 없이 `codex plugin add unreal-agent@codex-skills`를 실행합니다. 기존 설치·활성화 상태는 보존합니다 (비활성 상태도 유지). 다른 source나 확인 불가능한 로컬 checkout이면 runner 설치 전 중단하며 등록/Plugin을 변경하지 않습니다. Codex 변경 전에 `$CODEX_HOME/backups/unreal-agent-install.*` (기본 `~/.codex`)에 config.toml(있으면)과 marketplace/Plugin inventory를 저장합니다. 실패 시 백업을 보존하지만 Codex CLI의 내부 변경을 자동 복구하지 않으므로 메시지와 백업을 확인하고 재실행하세요. `--runner-only`는 Codex 설치를 건너뜁니다. 다른 Plugin·인증을 제거하거나 갱신하지 않습니다.

외부 `unreal-agent-runner`를 별도로 설치하고 사용할 provider의 인증·모델 접근을 준비해야 합니다. Plugin은 실행기 바이너리, 인증 정보, MCP 서버, app, hook을 설치하지 않으며 marketplace의 `ON_INSTALL`은 runner 인증을 제공한다는 뜻이 아닙니다. 원본의 `/Users/oozoofrog/.local/bin/unreal-agent-runner`는 한 Mac의 설치 예이고, `openai-codex` / `gpt-6-astra`는 과거 smoke run 관측값입니다. 현재 환경에서 runner 경로·옵션·모델 가용성을 확인하고 작업에 맞는 runner 모델·thinking level을 선택합니다. 사용자 지정 값은 보존하며, 현재 Codex 대화의 모델 설정은 바뀌지 않습니다. runner가 없으면 제한을 알리고 임의로 Codex 실행으로 대체하지 않습니다.

[스킬 본문](../unreal-agent/SKILL.md)은 절대 workspace 경로, 안전한 JSON 요청, JSONL 이벤트·종료 상태 수집과 결과 검토를 안내합니다. 한 실행은 한 요청 후 종료하며, 이어서 작업하려면 같은 `session_id`와 세션 디렉터리를 재사용합니다. 지속적인 Codex 채팅으로 전환되는 것은 아닙니다. Git·외부 효과는 사용자가 허용한 범위만 수행합니다.

이번 등록의 검증 범위는 배포 inventory, 원본/미러 바이트·모드 일치, 명시적 호출 메타데이터, skills-only 구성, 문서 링크와 정적 validator입니다. 실제 runner 실행·인증·모델 응답, Plugin 설치 및 새 세션의 스킬 노출은 별도로 확인해야 합니다. 과거 smoke run 언급을 이번 배포본의 실행 검증으로 해석하지 않습니다.

## Local AI Studio

`local-ai-studio`는 Local AI Studio를 사용한 이미지·음성·영상·음악·영어→한국어 번역 작업을 수행하는 skills-only Plugin `0.2.1`입니다. Local AI Studio 또는 온디바이스 모델 작업을 요청했는데 LocalAIHub나 필요한 모델 그룹이 없으면 현재 소스를 확인해 로컬에 설치한 뒤 결과를 검증·전달합니다. 일반 미디어 요청만으로 설치를 시작하지 않습니다. 새 작업에서 `$local-ai-studio` 또는 `$local-ai-studio:local-ai-studio`로 호출할 수 있으며 사용자가 선택한 도구·모델·출력 위치·형식을 우선합니다.

아직 푸시하지 않은 checkout을 시험하려면 저장소 루트에서 `codex plugin marketplace add "$PWD"`로 등록한 뒤 `codex plugin add local-ai-studio@codex-skills`를 사용하세요. 기존 `codex-skills` marketplace가 있으면 source가 원격인지 해당 checkout인지 먼저 확인합니다. Standalone을 선택하면 `local-ai-studio/`를 skill-installer로 설치하되 Plugin과 중복 설치하지 않고 기존 전역 스킬을 임의로 덮어쓰지 않습니다.

Plugin 설치 자체는 LocalAIHub나 모델을 설치하지 않습니다. 스킬을 호출해 로컬 작업을 요청하면 Apple Silicon/macOS와 저장 공간을 확인하고 [LocalAIHub 설치 절차](../local-ai-studio/references/setup.md)로 필요한 소스·앱·모델 그룹을 준비할 수 있습니다. 이미 설치된 경우 `ai --help`, `ai status`, `ai models`와 선택 root/`AIHUB_ROOT`를 확인해 재다운로드를 피합니다. 참조 Mac의 `/Volumes/eyedisk/AI/bin/ai`와 `/Volumes/eyedisk/AI/LocalAIHub/README.md`는 발견 후보일 뿐 타 기기의 기본 경로가 아닙니다. 모델·생성 미디어·인증·runner·MCP·app·hook을 Plugin에 번들하지 않으며 marketplace `ON_INSTALL`도 모델 라이선스 동의나 인증을 대신하지 않습니다.

Qwen Image 2.1 설치 플래그는 사용자의 명시적 라이선스 동의 후에만 사용합니다. 24 GB Mac에서는 다른 app/UI 작업도 포함해 대형 생성 모델을 직렬로 실행합니다. TTS 출력 디렉터리·전사 stem·그 외 파일 경로의 차이와 `music --prompt`/bare `music`의 동작을 [명령 참고](../local-ai-studio/references/cli-workflows.md)에 정리했습니다.

Plugin 설치 성공, 새 세션에서 읽은 스킬 경로, 모델 readiness, 실제 추론 완료, 결과의 파일·형식·품질 확인은 별도 단계입니다. 배포 검사만으로 실제 생성·재생 품질이나 설치 후 노출을 주장하지 않습니다.
