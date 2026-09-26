# codex-skills

ChatGPT Chat·Work의 목적별 모델 선택과 상담과 응답 회수를 위한 `$gptplease`, Swift 의미론 탐색용 `swift-intelligence`, 개발 팀 구성과 협업을 위한 `astra-team-building`, Figma UI 작업용 `figma-computer-use`, 일반 Codex 세션의 작업 인계용 `session-continuity`, 켄트 벡의 글을 바탕으로 한 개발 절차 `ponytail-beck-tdd`, 명시적 외부 runner 호출용 `unreal-agent`, Local AI Studio 설치·모델 실행용 `local-ai-studio`를 제공합니다.

## Jev Start

`$jev-start`는 작업 시작 시 Jev/TypeSafe를 개발 보조로 선택적으로 활용하도록 하는 짧은 지침입니다. GPT가 현재 작업에서 이득이 있는 좁은 의미 판단을 골라 맡기고, 실제 호출이 필요할 때 기존 `typesafe-ai` 스킬을 읽습니다.

```text
$jev-start 이 저장소의 스킬 호출 조건을 검토하고 필요한 개선을 해주세요.
```

[스킬 본문](plugins/jev-start/skills/jev-start/SKILL.md)과 UI 메타데이터를 담은 skills-only Plugin `0.1.0`입니다. marketplace를 갱신한 뒤 `codex plugin add jev-start@codex-skills`로 설치하고 새 작업에서 `$jev-start` 또는 `$jev-start:jev-start`로 호출합니다. 저장소 전용 `.agents/skills/jev-start`는 Plugin 안으로 옮겨 중복 노출을 피합니다. 실제 Jev 호출에는 별도 `typesafe-ai` 스킬과 사용 가능한 API 인증이 필요합니다. 사용 가능 여부와 실제 호출 결과를 구분하며, 별도 실행기·매 턴 호출·현재 모델/effort 변경을 제공하지 않습니다. [설치 안내](docs/plugin-installation.md#jev-start)를 참고하세요.

## GPT Please

`gptwork`를 **gptplease**로 이름 변경하고 Chat·Chat Pro 상담과 목적·복잡도에 따른 모델·사고 수준 선택을 통합했습니다. 기존 `gptpro` Skill·Plugin·전용 Runner/전송 런타임 및 전용 설치 도구는 제거했습니다. 과거 상담 패키지·로그인 프로필을 삭제하거나 새 스킬로 이관하지 않습니다.

```text
$gptplease Chat Pro로 선택한 파일을 검토하고 완료 응답을 여기서 처리해주세요.
$gptplease Work에서 Astra로 이 기획안을 검토하고 답변을 가져와 주세요.
```

- Chat·Work의 실제 선택기에서 목적·복잡도·시간 및 비용 제한에 맞는 모델과 사고 수준을 고릅니다. Work는 실제 제공되는 GPT-6 Luna High·Sol Medium/High·Astra High/Extra High를 작업에 맞춰 선택하고, Chat은 실제 Chat 후보만 사용합니다. 화면별 모델·effort를 일괄 치환하지 않습니다.
- 모델·사고 수준을 명시하면 그대로 지키고 나머지만 자동 선택합니다. `Chat Pro`는 Pro를, `Chat Astra Pro`는 모델까지 요구합니다. 명시한 조합이 없으면 전송을 보류합니다.
- 모드를 생략한 새 요청은 Work를 사용합니다. 자동 선택은 같은 모드의 가용 후보 안에서 조정하며 Ultra·Fast/priority를 자동 활성화하지 않습니다.
- 승인된 파일은 실제 업로드하며, 같은 입력창에서 모드·설정·첨부를 확인한 뒤 한 번 전송합니다.
- 호출 세션이 최종 응답 완료를 기다리고 전체 내용을 읽어 검토·답변·허용된 수정을 이어갑니다.

지원되는 브라우저 제어와 ChatGPT 로그인이 필요합니다. 번들 상담 모듈은 같은 브라우저 도구 세션에서 실행되며, Codex 모델·provider 설정을 바꾸거나 별도 서버를 열지 않습니다. [전송 계약](gptplease/references/transport-contract.md)과 [실제 검증 범위](gptplease/references/runtime-validation.md), [설치·계정 검증 기록](docs/gptplease-transport-validation.md)를 참고하세요. 기존 패키지의 자동 비밀정보 검사·불변 승인·영구 전송 기록·서명 스트림/전용 복구를 제공한다고 주장하지 않습니다. 코드 상담과 응답 회수 용도를 통합한 것이며, 공개 범위와 독립 검증은 호출 세션이 책임집니다. [사용 안내](gptplease/README.md), [모델 선택](gptplease/references/model-selection.md), [입력창 설정](gptplease/references/composer-settings.md), [파일 첨부](gptplease/references/file-attachments.md)를 참고하세요.

## Session Continuity

`$session-continuity`는 일반 Codex 세션용 Session Rotation Protocol을 저장소에 초기화합니다. 리더/워커 없이 `AGENTS.md`의 지속 규칙과 `.codex/work/<task-id>.md`를 사용해 작업 시작, 새 세션 재개, checkpoint와 완료 정리를 지원합니다.

```text
$session-continuity로 현재 저장소를 초기화하고 task 467의 목표와 완료 조건을 기록하세요.
$session-continuity로 task 467을 재개하고 현재 Git 상태와 대조한 뒤 Exact Next Action부터 계속하세요.
```

기존 규칙·템플릿·task state를 보존하며 `.gitignore` 수정은 선택 사항입니다. 실제 실행하지 않은 검증은 `NOT RUN`으로 기록하고, 완료 후 장기 결론을 정식 문서 등에 반영한 뒤 state 삭제/보관을 안내합니다. 자동 압축 감지·새 세션 생성·commit은 포함하지 않습니다. 보조 도구는 Python 3.9+와 Git만 사용합니다. [설치와 사용 안내](session-continuity/README.md), [검증 기록](session-continuity/VALIDATION.md)을 참고하세요.

## Ponytail + Beck TDD

`$ponytail-beck-tdd`는 구현과 기존 테스트 점검·개선에 명시적으로 선택하는 스킬입니다. 새 동작은 켄트 벡의 TDD 순환으로 개발하고, 기존 테스트는 요구사항·실제 호출자·구현과 대조해 동작 보장, 진단력, 안정성과 유지비를 개선합니다. Ponytail의 유지보수 가능한 최소 구현 원칙을 함께 적용합니다.

```text
$ponytail-beck-tdd로 저장 요청이 중복 처리되는 버그를 재현하고 수정해주세요.
$ponytail-beck-tdd로 기존 구현과 테스트를 점검하고 개선안을 보고해주세요. 파일은 수정하지 마세요.
$ponytail-beck-tdd로 기존 동작을 보존하면서 테스트의 검증과 구성을 개선하고 효과를 확인해주세요.
```

작은 테스트를 큰 테스트로 바꾸면서 의무적으로 삭제하지 않습니다. 테스트 전체의 신뢰성·속도·진단력을 함께 다듬고, 통합·관통 테스트는 실제 연결과 상호작용을 확인할 때 사용합니다. 벡이 작성하거나 공인한 스킬은 아닙니다. 일반 코딩 요청에는 자동 적용하지 않으며, 별도 Ponytail 설치·MCP 서버·실행기·전역 개인 지시 변경 없이 사용할 수 있습니다. [스킬 본문](ponytail-beck-tdd/SKILL.md), [근거와 해석](ponytail-beck-tdd/references/kent-beck.md), [설치 안내](docs/plugin-installation.md)를 참고하세요.

점검 요청은 근거와 개선안을 보고하고, 개선 요청은 필요한 변경과 검증까지 수행합니다. 기존 동작의 테스트 보강은 처음부터 통과할 수 있으며, 실패하면 기대값·환경·제품 결함을 구분합니다. 커버리지 증가는 참고 지표로 사용하고 구체적인 이득과 보장 보존으로 변경을 채택합니다. [기존 테스트 개선 절차](ponytail-beck-tdd/references/existing-tests.md), [실제 사례와 설계 근거](ponytail-beck-tdd/references/test-improvement-research.md)를 참고하세요.

## Unreal Agent

`$unreal-agent`는 사용자가 Unreal Agent 사용을 명시적으로 요청할 때만 별도 로컬 `unreal-agent-runner`에 한정된 작업을 맡기고, Codex가 변경 사항과 결과를 직접 검토하는 스킬입니다. 실행할 때 작업의 범위·난이도에 맞춰 runner의 Codex 모델과 thinking level을 자동으로 고르며 사용자 지정 값은 유지합니다. 현재 Codex 대화의 모델 설정을 바꾸지는 않습니다. 일반 코딩이나 이름에 Unreal이 포함된 Unreal Engine 작업에 자동 적용하지 않습니다.

```text
$unreal-agent로 현재 저장소의 지정한 버그를 수정하고 결과를 검토해주세요. 커밋과 푸시는 하지 마세요.
```

Standalone `unreal-agent/`와 byte-identical skills-only Plugin `0.1.3`를 제공합니다. runner 실행 파일·인증 정보·MCP·app·hook은 포함하지 않습니다. 별도 runner 설치와 해당 provider의 인증·모델 가용성이 필요하며, 없으면 한계를 알리고 Codex로 조용히 대체하지 않습니다. 스킬에 적힌 로컬 설치 경로와 과거 smoke run 모델은 이식 가능한 기본값이 아닙니다.

Go 1.27+, Git, Python 3.9+, Codex CLI가 있으면 다음 한 명령으로 upstream runner와 Codex Plugin을 설치할 수 있습니다.

```bash
curl -fsSL https://raw.githubusercontent.com/oozoofrog/codex-skills/main/scripts/install_unreal_agent.sh | bash
```

설치기는 기존 marketplace source와 Plugin 상태를 먼저 검사합니다. 미등록이면 원격 marketplace와 Plugin을 설치하고, 의도한 원격 source는 필요할 때 갱신하며, 같은 저장소의 로컬 checkout은 등록을 유지합니다. 다른 source면 변경 없이 중단합니다. Codex 변경 전에 config와 설치 목록을 백업하고 다른 Plugin·인증은 건드리지 않습니다. 비활성화된 기존 Plugin은 그대로 두며 새 Codex 대화에서 노출을 확인하세요. 기존 미관리 바이너리는 덮어쓰지 않습니다.

[스킬 본문](unreal-agent/SKILL.md)과 [설치 안내](docs/plugin-installation.md#unreal-agent)를 참고하세요. 배포 검사는 구조·메타데이터·미러 일치를 확인할 뿐 실제 runner 실행, 인증, 모델 응답이나 새 세션 노출을 보장하지 않습니다. 실행 시 runner의 작업과 Codex가 직접 확인한 검증을 구분해 보고합니다.

## Local AI Studio

`$local-ai-studio`는 Apple Silicon Mac에서 Local AI Studio의 `ai` CLI로 이미지 생성·편집, 음성 합성·전사, 영상·음악 생성, 영어→한국어 번역을 실행하고 결과물을 검증·전달합니다. Local AI Studio 또는 온디바이스 모델 작업을 요청했는데 LocalAIHub나 필요한 모델이 없으면 해당 소스와 요청에 필요한 모델 그룹만 로컬에 설치한 뒤 작업을 이어갑니다. 일반 미디어 요청만으로 대용량 설치를 시작하지 않으며, 사용자가 지정한 도구·모델·저장 위치·형식을 우선합니다.

```text
$local-ai-studio로 이 녹음을 전사해 지정한 폴더에 SRT로 저장하고 결과를 확인해주세요.
$local-ai-studio로 비상업적 평가용 찻주전자 이미지를 만들고 PNG 파일을 확인해주세요.
$local-ai-studio로 이 영어 문서를 한국어로 번역해 지정한 TXT 파일로 저장해주세요.
```

Standalone `local-ai-studio/`와 byte-identical skills-only Plugin `0.2.1`을 제공합니다. Plugin에 모델·런타임·생성 미디어·인증·실행기 바이너리는 포함하지 않습니다. 설치 시 현재 소스·CLI 기능, 선택한 저장 위치와 용량을 확인하고 필요한 모델만 받습니다. `/Volumes/eyedisk/AI`는 참조 Mac의 발견 후보일 뿐 보편적인 기본값이 아닙니다. Qwen Image 다운로드에는 사용자의 명시적 라이선스 동의가 필요합니다. 24 GB Mac에서는 대형 생성 모델을 한 번에 하나만 실행합니다.

설치 후 `ai --help`로 지원 명령을 확인합니다. 공개 LocalAIHub 소스와 다른 로컬 체크아웃의 기능이 다를 수 있습니다. `READY`·종료 코드·`Output:` 로그만으로 결과 품질을 주장하지 않으며 실제 파일·형식·미리보기/재생/내용 확인 여부를 구분해 전달합니다. [스킬 본문](local-ai-studio/SKILL.md), [LocalAIHub 설치](local-ai-studio/references/setup.md), [명령·출력 규칙](local-ai-studio/references/cli-workflows.md), [Plugin 설치 안내](docs/plugin-installation.md#local-ai-studio)를 참고하세요.

## 다른 Plugin

`swift-intelligence`는 Xcode의 SourceKit-LSP로 Swift 정의, 참조, 구현, 타입, 심볼 및 진단을 읽기 전용으로 조회합니다. MCP 서버가 필요한 Plugin이므로 `plugins/swift-intelligence/`에만 제공합니다. Python 3 외의 Python 패키지나 외부 MCP 바이너리를 추가로 설치하지 않습니다.

`astra-team-building`은 프로젝트 개발을 위한 팀 구성·위임·재편을 요청할 때 사용하는 스킬입니다. Astra·Sol·Luna와 thinking level을 난도·불확실성·검증 가능성에 맞춰 배정하고, 독립 과제·실제 슬롯·격리 환경·공유 자원·통합 여력에 따라 팀 규모를 조절합니다. 작은 작업은 리더 단독으로 완료할 수 있으며 역할마다 세션을 만들거나 세 모델을 모두 쓸 의무는 없습니다. 현재 리더의 설정과 한 worktree 한 writer 원칙을 보존합니다. 스킬 자체의 설명·편집이나 일반 단일 작업에는 자동 적용하지 않습니다. [Astra Team Building 설치와 사용](plugins/astra-team-building/README.md)을 참고하세요. [교체 검증 기록](docs/astra-team-building-validation.md)에 로컬 설치·로더·독립 예제의 확인 범위를 정리했습니다.

`figma-computer-use`는 Figma MCP 대신 computer-use로 Figma 데스크톱·브라우저 UI를 조작합니다. 디자인 생성·편집·검증과 매뉴얼·호환성 기준 갱신을 지원합니다.

## Figma Computer Use

`$figma-computer-use`는 파일·페이지·선택 레이어를 확인하고, 접근성 정보와 스크린샷으로 Figma를 조작한 뒤 속성·렌더링·저장·프로토타입·내보내기 결과를 요청에 맞게 검증합니다. 별도 Figma MCP 서버나 토큰을 사용하지 않으며, 호스트의 `mcp__cua_repl.js` computer-use와 Figma 접근 권한이 필요합니다.

```text
$figma-computer-use 이 Figma 파일의 로그인 화면을 computer-use로 편집하고 결과를 확인해주세요.
$figma-computer-use 매뉴얼을 최신 Figma에 맞춰 갱신하고 버전업해주세요.
```

공식 매뉴얼의 탐색, 프레임·Auto layout, 컴포넌트·변수, 프로토타입, 내보내기·저장 절차를 [내부 사용 매뉴얼](figma-computer-use/references/figma-manual.md)에 정리했습니다. [출처 기록](figma-computer-use/references/sources.md)은 공식 문서 10개, 로컬 자료의 적용/제외 판단과 확인 날짜를 담습니다. MCP 가이드의 API 예제와 Figma 웹사이트 스타일 규칙을 일반 UI 조작에 적용하지 않습니다.

[버전 관리 절차](figma-computer-use/references/maintenance.md)는 스킬 `0.1.1`, 로컬 Figma `126.8.18`, 웹 제품 릴리스, computer-use API를 따로 추적합니다. 새 세션에서 로컬 버전과 검토 날짜를 확인하고, 필요한 공식 릴리스·매뉴얼만 갱신합니다. 영구 갱신 요청에는 원본·호환성 기록·Plugin 버전·미러·CHANGELOG·검증을 함께 처리합니다. 이는 사용 시 확인/요청 시 갱신하는 절차이며 백그라운드 감시나 앱 자동 업데이트를 설치하지 않습니다.

Figma `126.8.18` 네이티브 앱에서 프레임·한글 텍스트·Auto layout·컴포넌트/variant/instance·색상 변수·텍스트 스타일, 프로토타입 이동/뒤로 가기, PNG 내보내기/가져오기를 실제 검증했습니다. 필드 포커스와 값 커밋, 숫자 입력, 붙여넣기 타임아웃 및 연결 복구 지침을 `0.1.1`에 반영했습니다. 브라우저 편집은 로그인/연결 오류로 차단됐고 클라우드 저장·이름 있는 버전 저장과 고급 기능은 미확인입니다. 자세한 범위와 증거는 [기능 검증 보고서](docs/figma-computer-use-validation.md)를 참고하세요. 배포는 `figma-computer-use/` standalone과 byte-identical Plugin 미러를 제공하며 Plugin 설치 경로를 사용합니다. 설치 방법은 [Plugin 설치](docs/plugin-installation.md)를 참고하세요.

## 모델 역할 분담과 평가

[이번 릴리스 변경 기록](docs/model-routing-changelog.md)을 별도로 정리했으며 기존 CHANGELOG 이력은 보존합니다.

[원문 확인 범위·적용 설계·사용 예시](docs/model-routing-review.md)에 Chat/Work 후보, 선택형 혼합 모델, 외부 runner 경계와 task state 연결을 정리했습니다. 새 운영 스킬은 추가하지 않습니다. 일반 단일 세션은 그대로 사용합니다.

`scripts/model_routing_eval.py`는 세 정책의 **기록된 결과를 오프라인으로 검사·집계**합니다. 합성 fixture 통과를 실제 모델 품질이나 비용 절감으로 보고하지 않습니다. [검증 기록과 미실행 항목](docs/model-routing-validation.md)을 구분해 확인하세요.

## 설치

필요한 Plugin만 선택해 설치합니다. 아래 명령은 해당 변경이 원격 marketplace에 반영된 뒤 사용할 수 있습니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add gptplease@codex-skills
codex plugin add session-continuity@codex-skills
codex plugin add unreal-agent@codex-skills
codex plugin add local-ai-studio@codex-skills
```

설치 후 새 대화에서 `$gptplease`를 호출합니다. 이전 `gptwork`/`gptpro` 설치본의 중복 노출을 정리하되 과거 패키지와 계정 프로필은 보존합니다. 다른 Plugin의 요구 사항과 standalone 설치는 [Plugin 설치 안내](docs/plugin-installation.md)를 참고하세요.

## 검증

```bash
python3 -m unittest discover -s scripts/tests -v
python3 scripts/sync_skill_mirrors.py --package gptplease
node --test gptplease/tests/*.test.mjs
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py gptplease
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/gptplease
python3 scripts/sync_skill_mirrors.py --package unreal-agent
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py unreal-agent
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/unreal-agent/skills/unreal-agent
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/unreal-agent
python3 scripts/sync_skill_mirrors.py --package local-ai-studio
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py local-ai-studio
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/local-ai-studio/skills/local-ai-studio
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/local-ai-studio
git diff --check
```

Swift Intelligence를 수정할 때는 해당 Plugin의 검증 지침을 별도로 따릅니다. 변경 기록은 [CHANGELOG.md](CHANGELOG.md)에 있습니다.
