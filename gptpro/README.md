# gptpro

`gptpro`는 Codex가 macOS ChatGPT 앱의 로그인된 ChatGPT Pro와 협업하도록 돕는 Skill입니다.

```text
사용자: $gptpro 이 변경을 리뷰해주세요
Codex: 관련 코드 선택 및 비밀 검사
       → 읽기 전용 MCP package 승인/활성화
       → ChatGPT 앱의 새 Chat에서 1회 전송
       → 응답 회수
       → 로컬 코드로 독립 검증
```

ChatGPT Pro는 조언자입니다. 실제 파일 수정, shell, build/test, Git 작업은 Codex만 수행합니다.

## 가장 중요한 사용 모델

- Codex에서 보이는 Skill 이름은 `GPT Pro Collaborator`입니다.
- ChatGPT 앱에서 실제로 선택하는 읽기 전용 App 이름은 `gptpro`입니다. 두 이름은 같은 화면 이름이 아닙니다.
- `gptpro` ChatGPT App과 Tunnel 프로필은 **사용자 계정에 한 번** 연결합니다.
- 프로젝트마다 앱을 다시 만들지 않습니다.
- 각 요청에서는 “이번에 어떤 저장소 파일을 얼마나 읽을 수 있는가”를 고정한 작은 package만 새로 만듭니다.
- 범위 제한형 상시 승인을 만들면 조건이 맞는 package는 매번 다시 묻지 않습니다.

## 요구 사항

- macOS ChatGPT 앱에 로그인된 상태
- 일반 `Chat`에서 사용할 수 있는 `Pro`
- Codex의 Computer Use/Accessibility 접근
- ChatGPT Developer Mode에 연결되어 있고 ChatGPT Plugins에서 `gptpro`로 보이는 읽기 전용 App
- OpenAI Secure MCP Tunnel 프로필
- Python 3.11 이상

Browser나 Chrome은 사용하지 않습니다. CDP, `--remote-debugging-port`, Electron 내부 bridge/IPC, 비공개 ChatGPT endpoint도 사용하지 않습니다.

## 설치

저장소 루트에서 다음 한 명령을 실행합니다. 기본 설치는 `gptpro-mcp` companion도 함께 설치합니다.

```bash
python3 scripts/manage_skills.py install gptpro
```

업데이트:

```bash
python3 scripts/manage_skills.py install gptpro --update
```

ChatGPT App ID를 저장소에 넣지 않고 로컬 owner-only plugin으로 결속하려면, App ID만 들어 있는 mode `0600` 파일을 준비한 뒤 실행합니다.

```bash
python3 scripts/manage_skills.py desktop-bind \
  --app-id-file /absolute/private/app-id.txt \
  --dry-run

python3 scripts/manage_skills.py desktop-bind \
  --app-id-file /absolute/private/app-id.txt \
  --confirm-bind
```

결과에는 App ID 자체가 아니라 hash만 표시됩니다. 생성된 `.app.json`과 binding receipt는 `~/Library/Application Support/gptpro/desktop/v2/` 아래 mode `0600`으로 저장됩니다.

## 사용

새 Codex 작업에서 자연스럽게 요청합니다.

```text
$gptpro 현재 변경의 버그 가능성과 빠진 테스트를 리뷰해주세요.
```

지원 모드는 `plan`, `ask`, `review`, `debug`, `architecture`입니다. 자세한 첫 사용과 운영 절차는 [references/user-manual.md](references/user-manual.md)를 참고하세요.

ChatGPT 앱에서는 Plugins에서 `gptpro`를 찾아 “채팅에서 사용해 보기”를 선택합니다. 이 동작이 `Work`를 열면 `Chat`으로 전환한 뒤에도 composer의 `gptpro` pill이 남아 있고 `Pro`가 선택되어 있는지 확인합니다. App 이름이 바뀌었다면 기존 승인 패키지를 재사용하지 말고, 화면에 보이는 새 이름으로 새 package를 준비·승인합니다.

## 승인

두 방식이 있습니다.

- exact-package 승인: 이번 요청의 정확한 파일·hash·예산만 승인
- machine-global standing approval: 모든 로컬 Git 저장소에서 같은 App/Tunnel/model과 지정된 경로·모드·예산 안의 요청을 일정 기간 승인

상시 승인은 선택된 untracked 파일, 외부 문서, 비밀 탐지, 예산 초과, App/workspace/model 변경을 포함하지 않습니다. 범위를 벗어나면 새 승인이 필요합니다.

## 저장 위치

새 Desktop 상태는 저장소가 아니라 다음 owner-only 위치에 둡니다.

```text
~/Library/Application Support/gptpro/desktop/v2/
```

따라서 일반 사용은 프로젝트에 `.gptpro`를 만들지 않습니다. 디렉터리는 `0700`, 파일은 `0600`, 쓰기는 atomic이며 symlink·hard link·잘못된 소유권을 거부합니다.

## 안전 규칙

- 비밀 검사 후에만 공개
- 읽기 전용 MCP 도구만 제공
- 새 general Chat과 `Pro`를 화면에서 확인
- Send 최대 1회
- 모호한 전송은 자동 재전송 금지
- 응답은 exact request nonce와 outbound hash에 결속
- 숨은 Web/Browser fallback 없음
- CDP/Electron 내부 API 없음
- Pro 조언은 적용 전 로컬 검증

## 검증

```bash
python3 -m unittest discover -s gptpro/tests -v

python3 gptpro/scripts/validate_structure.py \
  --skill-dir gptpro \
  --mirror plugins/gptpro/skills/gptpro \
  --json

python3 -m py_compile \
  gptpro/scripts/gptpro.py \
  gptpro/scripts/validate_structure.py
```

실제 로그인된 ChatGPT 앱 E2E는 로컬 단위 테스트와 별개의 attended evidence입니다. 새로운 prompt 전송에는 해당 package의 유효한 승인과 화면상 1회 Send 확인이 필요합니다.
