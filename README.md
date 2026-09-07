# codex-skills

ChatGPT Chat·Work의 목적별 모델 선택과 상담과 응답 회수를 위한 `$gptplease`, Swift 의미론 탐색용 `swift-intelligence`, 역할별 작업 조정을 위한 `astra-orchestrator`를 제공합니다.

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

## 다른 Plugin

`swift-intelligence`는 Xcode의 SourceKit-LSP로 Swift 정의, 참조, 구현, 타입, 심볼 및 진단을 읽기 전용으로 조회합니다. MCP 서버가 필요한 Plugin이므로 `plugins/swift-intelligence/`에만 제공합니다. Python 3 외의 Python 패키지나 외부 MCP 바이너리를 추가로 설치하지 않습니다.

`astra-orchestrator`는 Astra 리더·워커·Git 전용 워커로 작업 조정을 요청할 때 사용하는 스킬입니다. 작은 작업은 현재 리더가 직접 완료하고 병렬화가 유리할 때만 위임합니다. 스킬 자체의 설명·편집이나 일반 단일 작업에는 자동 적용하지 않습니다. 내부 병렬 과제는 서브에이전트, 사용자가 새 작업 생성을 명시한 장기 과제는 별도 Codex 작업을 선택할 수 있습니다. [Astra Orchestrator 설치와 사용](plugins/astra-orchestrator/README.md)을 참고하세요.

## 설치

필요한 Plugin만 선택해 설치합니다. 아래 명령은 해당 변경이 원격 marketplace에 반영된 뒤 사용할 수 있습니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add gptplease@codex-skills
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
