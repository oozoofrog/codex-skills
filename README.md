# codex-skills

ChatGPT Chat·Work의 목적별 모델 선택과 상담과 응답 회수를 위한 `$gptplease`, Swift 의미론 탐색용 `swift-intelligence`, 역할별 작업 조정을 위한 `astra-orchestrator`, Figma UI 작업용 `figma-computer-use`, 일반 Codex 세션의 작업 인계용 `session-continuity`를 제공합니다.

## GPT Please

`gptwork`를 **gptplease**로 이름 변경하고 Chat·Chat Pro 상담과 목적·복잡도에 따른 모델·사고 수준 선택을 통합했습니다. 기존 `gptpro` Skill·Plugin·전용 Runner/전송 런타임 및 전용 설치 도구는 제거했습니다. 과거 상담 패키지·로그인 프로필을 삭제하거나 새 스킬로 이관하지 않습니다.

```text
$gptplease Chat Pro로 선택한 파일을 검토하고 완료 응답을 여기서 처리해주세요.
$gptplease Work에서 Astra로 이 기획안을 검토하고 답변을 가져와 주세요.
```

- Chat·Work의 실제 선택기에서 목적·복잡도·시간 및 비용 제한에 맞는 모델과 사고 수준을 고릅니다. 명확한 추출은 Luna Light, 일반 작업은 Terra Medium, 깊은 분석은 Sol High, 어려운 다단계 작업은 Astra High/Extra High를 시작점으로 삼습니다.
- 모델·사고 수준을 명시하면 그대로 지키고 나머지만 자동 선택합니다. `Chat Pro`는 Pro를, `Chat Astra Pro`는 모델까지 요구합니다. 명시한 조합이 없으면 전송을 보류합니다.
- 모드를 생략한 새 요청은 Work를 사용합니다. 자동 선택은 같은 모드의 가용 후보 안에서 조정하며 Ultra·Fast/priority를 자동 활성화하지 않습니다.
- 승인된 파일은 실제 업로드하며, 같은 입력창에서 모드·설정·첨부를 확인한 뒤 한 번 전송합니다.
- 호출 세션이 최종 응답 완료를 기다리고 전체 내용을 읽어 검토·답변·허용된 수정을 이어갑니다.

지원되는 브라우저 제어와 ChatGPT 로그인이 필요합니다. 기존 패키지의 자동 비밀정보 검사·불변 승인·영구 전송 기록·서명 스트림/전용 복구를 제공한다고 주장하지 않습니다. 코드 상담과 응답 회수 용도를 통합한 것이며, 공개 범위와 독립 검증은 호출 세션이 책임집니다. [사용 안내](gptplease/README.md), [모델 선택](gptplease/references/model-selection.md), [입력창 설정](gptplease/references/composer-settings.md), [파일 첨부](gptplease/references/file-attachments.md)를 참고하세요.

## Session Continuity

`$session-continuity`는 일반 Codex 세션용 Session Rotation Protocol을 저장소에 초기화합니다. 리더/워커 없이 `AGENTS.md`의 지속 규칙과 `.codex/work/<task-id>.md`를 사용해 작업 시작, 새 세션 재개, checkpoint와 완료 정리를 지원합니다.

```text
$session-continuity로 현재 저장소를 초기화하고 task 467의 목표와 완료 조건을 기록하세요.
$session-continuity로 task 467을 재개하고 현재 Git 상태와 대조한 뒤 Exact Next Action부터 계속하세요.
```

기존 규칙·템플릿·task state를 보존하며 `.gitignore` 수정은 선택 사항입니다. 실제 실행하지 않은 검증은 `NOT RUN`으로 기록하고, 완료 후 장기 결론을 정식 문서 등에 반영한 뒤 state 삭제/보관을 안내합니다. 자동 압축 감지·새 세션 생성·commit은 포함하지 않습니다. 보조 도구는 Python 3.9+와 Git만 사용합니다. [설치와 사용 안내](session-continuity/README.md), [검증 기록](session-continuity/VALIDATION.md)을 참고하세요.

## 다른 Plugin

`swift-intelligence`는 Xcode의 SourceKit-LSP로 Swift 정의, 참조, 구현, 타입, 심볼 및 진단을 읽기 전용으로 조회합니다. MCP 서버가 필요한 Plugin이므로 `plugins/swift-intelligence/`에만 제공합니다. Python 3 외의 Python 패키지나 외부 MCP 바이너리를 추가로 설치하지 않습니다.

`astra-orchestrator`는 Astra 리더·워커·Git 전용 워커로 작업 조정을 요청할 때 사용하는 스킬입니다. 작은 작업은 현재 리더가 직접 완료하고 병렬화가 유리할 때만 위임합니다. 스킬 자체의 설명·편집이나 일반 단일 작업에는 자동 적용하지 않습니다. 내부 병렬 과제는 서브에이전트, 사용자가 새 작업 생성을 명시한 장기 과제는 별도 Codex 작업을 선택할 수 있습니다. [Astra Orchestrator 설치와 사용](plugins/astra-orchestrator/README.md)을 참고하세요.

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

## 설치

필요한 Plugin만 선택해 설치합니다. 아래 명령은 해당 변경이 원격 marketplace에 반영된 뒤 사용할 수 있습니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add gptplease@codex-skills
codex plugin add session-continuity@codex-skills
```

설치 후 새 대화에서 `$gptplease`를 호출합니다. 이전 `gptwork`/`gptpro` 설치본의 중복 노출을 정리하되 과거 패키지와 계정 프로필은 보존합니다. 다른 Plugin의 요구 사항과 standalone 설치는 [Plugin 설치 안내](docs/plugin-installation.md)를 참고하세요.

## 검증

```bash
python3 -m unittest discover -s scripts/tests -v
python3 scripts/sync_skill_mirrors.py --package gptplease
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py gptplease
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/gptplease
git diff --check
```

Swift Intelligence를 수정할 때는 해당 Plugin의 검증 지침을 별도로 따릅니다. 변경 기록은 [CHANGELOG.md](CHANGELOG.md)에 있습니다.
