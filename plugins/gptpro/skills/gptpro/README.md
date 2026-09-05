# gptpro 0.6 — 기능 이름과 정의

`gptpro`는 Codex가 선택하고 승인받은 코드 스냅샷을 macOS ChatGPT 앱의 로그인된 ChatGPT Pro에 한 번 보내고, 답변을 자동으로 가져와 독립적으로 검토하는 Skill입니다. ChatGPT Pro는 조언을 제공하며 파일 수정, 테스트, Git 작업과 최종 판단은 Codex가 담당합니다.

사용자가 **`$gptpro`를 명시하여 plan, ask, review, debug, architecture 상담을 요청할 때만** 실행합니다. 일반 Codex 작업이나 OpenAI API 호출에는 자동으로 사용하지 않습니다. 현재 구현은 Schema 6, `inline-immutable-snapshot`, `desktop-electron`, 일반 Chat(`normal`)을 사용합니다.

## 기능 개요

아래 이름은 이 README에서 사용하는 대표 용어입니다. CLI 명령과 코드 식별자는 기존 이름을 유지합니다.

| 기능 이름 | 정의와 사용 목적 | 명령·식별자 |
| --- | --- | --- |
| **격리 Runner** | 기본 ChatGPT 앱과 별도 프로필로 실행되는 전용 ChatGPT 프로세스. 상담용 연결 환경을 분리합니다. | `desktop-launch`, `desktop-doctor` |
| **Launcher 실행기** | 격리 Runner를 여는 선택 설치형 macOS 앱. 반복 실행을 편하게 합니다. | `gptpro Launcher.app`, `launcher-install` |
| **명시적 파일 선택과 비밀정보 검사** | 지정한 파일 범위에 경로·UTF-8·비밀정보 검사를 적용해 공개 대상을 정합니다. | `prepare --include` 또는 `--file-list` |
| **불변 컨텍스트 패키지** | 질문, 선택 파일 원문, diff, 보충 문서를 해시로 결속한 전송 스냅샷. 검토한 내용과 보낼 내용을 일치시킵니다. | `outbound.md`, `manifest.json`, `verify` |
| **정확한 패키지 승인** | 한 패키지의 내용·공개 범위·모델·채널·유효기간을 승인합니다. | `approve`, `exact-package-v2` |
| **범위 제한 지속 승인** | 미리 검토한 저장소·경로·모델 등의 범위 안에서 후속 패키지의 승인을 재사용합니다. | `standing-approval-*`, `gptpro-standing-approval-v4` |
| **정확한 모델·연결 검증** | 실제 Runner와 로그인된 모델 목록이 승인한 조건에 맞는지 전송 전에 확인합니다. | `desktop-doctor`, `models`, `resolve_model` |
| **단일 전송과 재전송 방지** | 패키지별 전송 허가를 먼저 기록하고 사용자 메시지를 한 번만 POST합니다. | `consult`, `submission_dispatching` |
| **서명된 스트림 응답 수집** | POST가 지정한 signed WebSocket 스트림에서 순서와 완료 증거를 확인하며 답변을 받습니다. | `stream_handoff`, `signed-stream-handoff-v1` |
| **조건부 현재 대화 분기 검증** | 스트림의 분기 출처가 불명확할 때, 완료된 답변이 해당 대화의 현재 분기와 일치하는지 확인합니다. | `current_branch_proof` |
| **GET 전용 응답 복구** | 전송 이후 수집이 끊긴 패키지의 기존 답변을 읽기 요청만으로 회수합니다. | `collect-response`, `conversation-readback-v1` |
| **응답 자동 가져오기** | 수집·복구한 답변을 패키지에 연결된 원문과 wrapper로 저장하고 `imported` 상태로 만듭니다. | `response_imported`, `_finalize_response` |
| **해시 체인 실행 기록** | 준비·승인·전송·수집·가져오기·평가 사건을 순서와 해시로 연결한 로컬 기록입니다. | `receipt.json`, `status` |
| **Codex 독립 평가** | Pro 조언을 현재 파일과 테스트로 확인하고 채택 여부와 근거를 기록합니다. | `record-evaluation`, `evaluation.json` |

## 전체 흐름

`plan`은 계획 검토, `ask`는 질문, `review`는 변경 검토, `debug`는 원인 분석, `architecture`는 구조 검토에 사용할 상담 모드입니다. 모드별 지침이 달라져도 공개·승인·전송 경계는 같습니다.

```text
사용자의 명시적 $gptpro 요청
  → 관련 파일 범위 선택
  → 격리 Runner 실행, 연결·모델 확인
  → prepare: 비밀정보 검사 + 불변 패키지 생성 [전송 없음]
  → 공개 파일·원문·해시·크기·모델 확인
  → 정확한 패키지 승인 또는 범위에 맞는 지속 승인
  → consult: 승인 재검증 + submission_dispatching 기록
  → 사용자 메시지 POST 1회
  → 서명된 스트림 응답 수집
  → 필요한 경우 현재 대화 분기 검증
  → 응답 자동 가져오기 [imported]
  → Codex 독립 검토 + record-evaluation [evaluated]

전송 허가 기록 이후 프로세스 중단 또는 스트림 수집 실패
  → 같은 패키지의 collect-response [GET만 수행, 재전송 없음]
  → 응답 자동 가져오기
  → Codex 독립 평가
```

`prepare`는 전송하지 않고, `approve`는 승인을 기록합니다. 실제 사용자 메시지 전송은 `consult`가 수행합니다. `imported`는 답변을 저장했다는 뜻이며, 조언의 정확성이나 코드 적용 완료를 뜻하지 않습니다. 후속 질문은 새 패키지로 시작합니다.

## 실행 환경: Runner, Launcher, 모델 검증

**격리 Runner**는 설치된 `/Applications/ChatGPT.app`의 두 번째 프로세스입니다. 전용 owner-only 프로필 `~/Library/Application Support/gptpro/runner/v1/profile`과 loopback 포트 `127.0.0.1:9223`을 사용합니다. 기본 ChatGPT 앱은 동시에 열어 둘 수 있습니다. Runner는 기본 앱의 프로필·쿠키·토큰·Keychain 값을 복사하지 않으며, 필요하면 사용자가 Runner 창에서 로그인합니다. 이 격리는 실행 프로필을 분리하는 기능이며 별도 가상 머신이나 운영체제 보안 sandbox를 제공한다는 뜻은 아닙니다.

**Launcher 실행기**는 `~/Applications/gptpro Launcher.app`에 설치하는 작은 실행기입니다. ChatGPT 복사본이 아니며 원본 앱을 수정하지 않습니다. Login Item이나 상주 daemon을 추가하지 않고 어느 ChatGPT 프로세스도 자동 종료하지 않습니다. 설치하지 않아도 `desktop-launch`로 같은 Runner를 열 수 있습니다.

Launcher 표시명은 **gptpro Launcher**이며, 아이콘은 원본 ChatGPT 테마에 **주황색 실행 배지**를 더합니다. 이 이름·아이콘은 Launcher에 적용됩니다. 실행된 Runner의 Dock·Cmd-Tab·메뉴·기본 창은 여전히 ChatGPT로 표시되어 시각적으로 구별되지 않습니다. `launcher-status`도 `runner_native_identity_customized=false`를 보고합니다. 적용 범위와 안전상 제한, 아이콘 재생성은 [앱 표시명·아이콘](references/app-identity.md)을 확인하세요.

**정확한 모델·연결 검증**은 포트가 열렸다는 사실보다 더 많은 조건을 확인합니다. `desktop-doctor`는 현재 사용자 소유의 ChatGPT 프로세스, 전용 프로필, loopback listener, 정확히 하나의 `app://-/index.html` renderer와 Desktop bridge를 확인합니다. `models`와 전송 시 모델 해석은 로그인된 동적 목록에서 승인한 모델 ID와 thinking effort를 확인합니다. 기본 모델은 `gpt-5-6-pro`이며 다른 모델을 쓰려면 해당 ID로 패키지를 새로 준비하고 승인해야 합니다. 조건이 맞지 않으면 중단하며 모델이나 전송 경로를 임의로 바꾸지 않습니다.

`launcher-status`는 `stopped`, `runner_starting`, `runner_unverified`, `runner_verified`, `port_conflict`, `process_state_unknown`을 보고합니다. 최종 연결 판단은 `desktop-doctor`를 기준으로 합니다. 비기본 `--endpoint`는 개발 진단용이며 일반 Skill 사용 경로가 아닙니다.

## 공개 범위: 파일 선택과 불변 패키지

**명시적 파일 선택과 비밀정보 검사**는 `--include` 패턴 또는 `--file-list`의 정확한 경로 목록으로 시작합니다. 기본 선택 대상은 Git tracked 파일이며, `--exclude`로 범위를 줄일 수 있습니다. Untracked 파일은 `--allow-untracked`와 그 공개 범위에 맞는 승인이 필요합니다. 위험한 경로, symlink, 허용되지 않는 파일 형식·권한, UTF-8 위반, 탐지된 비밀정보 등은 거부합니다. 탐지기는 모든 비밀정보의 부재를 보장하지 않으므로 공개할 원문 확인이 필요합니다.

**불변 컨텍스트 패키지**는 선택 당시의 원문을 보존합니다. `outbound.md`에는 질문과 모드 지침, 정렬된 파일 블록, 선택 경로의 `git diff HEAD`, 선택적 보충 문서가 들어갑니다. 블록마다 경로 또는 label, 바이트 수와 SHA-256을 기록합니다. `manifest.json`은 Git 기준 상태와 공개 범위를 결속하고, `verify`는 패키지와 각 블록의 크기·해시를 재검증합니다. 준비 이후 live worktree의 변경을 자동 반영하지 않습니다.

전송할 `outbound.md`의 상한은 **256 KiB(262,144 bytes)**입니다. 넘으면 선택 범위를 줄여 새로 준비하며 자동 요약, 분할 전송, 잘라내기로 통과시키지 않습니다. 별도 ZIP은 만들지 않습니다. 저장소의 코드·diff·보충 문서 공개는 `outbound.md` 한 사용자 메시지에 담기며, 함께 보내는 고정 `system-prompt.md`도 해시와 승인에 결속됩니다.

저장소 밖의 텍스트가 필요할 때는 `--supplement LABEL=/absolute/path`로 추가합니다. 소유자·권한·크기 제한을 만족하는 일반 UTF-8 파일만 읽고, 전송 메타데이터에는 원래 절대 경로 대신 label과 패키지 내부 artifact 경로를 사용합니다. 보충 문서 본문도 공개 대상이며 전체 256 KiB 한도에 포함됩니다.

ChatGPT에는 live filesystem, shell, 파일 쓰기, build/test, Git, MCP 또는 임의 filesystem/network 도구를 제공하지 않습니다. 코드 블록과 모델 답변은 모두 검증 전 데이터로 취급합니다.

## 승인: 한 패키지와 후속 범위의 차이

**정확한 패키지 승인**(exact-package approval)은 검토한 패키지 하나에 적용됩니다. Manifest, prompt, outbound, system prompt 해시, 공개 바이트 수, 정확한 모델, `desktop-electron` 채널, 일반 Chat, inline 형식을 결속합니다. 전송과 공개 범위에 대한 명시적 확인이 모두 필요합니다. 기본 유효기간은 120분이며 1분부터 24시간까지 지정할 수 있습니다. 내용이나 모델을 바꾸면 기존 승인이 새 패키지를 대신하지 않습니다.

**범위 제한 지속 승인**(bounded standing approval)은 검토한 패키지의 선택 규칙을 바탕으로 이후 변경된 스냅샷까지 허용할 범위를 정합니다. 저장소 경로 identity, include/exclude 또는 exact-path 규칙, tracked 정책, supplement label, 모드, 정확한 모델, 채널, 일반 Chat, 크기 한도와 만료를 비교합니다. 유효기간은 1시간부터 30일까지이며 목록 조회와 철회가 가능합니다. 허용 범위 안에서 내용이 달라진 새 패키지를 승인할 수 있지만, 새 label·더 넓은 경로·다른 모델 등 범위를 벗어나면 승인이 필요합니다. 각 패키지의 비밀정보 검사와 해시 재검증은 계속 수행합니다.

`standing-approval-create`는 범위를 저장합니다. 이후 `consult --handoff-dir … --use-standing-approval`로 일치하는 승인을 적용하거나 `--standing-approval <approval-id>`로 지정할 수 있습니다. 지속 승인은 암묵적 Skill 호출이나 무제한 공개 허가가 아닙니다.

## 전송: 한 번의 POST와 재전송 방지

**단일 전송과 재전송 방지**는 “응답이 없으니 다시 보내도 된다”는 오판을 막습니다. Python controller와 Node child가 실제 읽은 원문 해시·크기·모델을 대조하고, controller가 승인을 다시 확인한 뒤 `submission_dispatching`을 영구 기록해야 child가 POST 허가를 받습니다. 기록에 실패하면 전송을 허가하지 않습니다. 패키지 lock과 state revision 검사도 중복·오래된 상태 갱신을 막습니다.

이 기록은 **전송을 허가했다는 경계**이며 서버 도착이나 답변 완료 증거는 아닙니다. 경계를 넘긴 뒤에는 결과가 불명확해도 같은 패키지로 다시 전송하지 않습니다. 이 기능은 로컬에서 중복 시도를 막으며 네트워크상의 “반드시 한 번 전달”을 보장하지 않습니다.

여기서 “한 번”은 사용자 메시지의 `POST /f/conversation`을 뜻합니다. 모델 조회, attestation, signed URL 획득, 조건부 GET 등 필요한 통신까지 HTTP 요청 한 번으로 제한한다는 뜻은 아닙니다.

## 수집과 분기 검증: 정상 consult 경로

**서명된 스트림 응답 수집**은 POST의 SSE 응답에서 raw `stream_handoff`를 먼저 식별합니다. 지정된 `conversation-*` topic의 signed URL을 얻어 renderer의 native WebSocket으로 연결하고, 인증된 구독 응답, `recovered`/`catchups`, 순서가 맞는 `delta`와 terminal `done`을 처리합니다. Conversation·turn identity와 parent stream-item 연결을 검사하며, 최종 assistant 본문·메시지 ID·`recipient=all` 증거까지 있어야 답변을 받아들입니다.

“서명된”은 서비스가 발급한 signed WebSocket URL과 인증된 topic 구독을 가리킵니다. 답변 문장마다 별도의 디지털 서명을 검증한다는 뜻은 아닙니다. Raw topic과 signed URL은 저장하지 않고 topic 해시와 완료 근거만 기록합니다. Handoff가 없으면 직접 응답으로 대체하지 않습니다. POST의 초기 handoff 대기는 60초, signed topic의 첫 항목 대기는 5초, 이후 idle 대기는 30초로 제한됩니다.

**조건부 현재 대화 분기 검증**은 다음 중 하나가 관찰될 때 추가로 필요합니다.

- Compact stream에 분기 소속이 아직 불명확한 tool-role 후보가 있는 경우
- Assistant 증거가 signed handoff 이전부터 시작된 경우
- Signed delta가 handoff 이전 상태를 이어받는 경우

Signed `done` 이후 이미 알고 있는 conversation 하나만 최대 30초 동안 GET으로 읽습니다. 결정적 user message ID와 outbound 원문, tool 경로가 없는 현재 분기, signed 결과와 같은 assistant ID·표시 본문을 요구합니다. 여기서 분기는 **ChatGPT 대화 분기**이며 Git branch가 아닙니다.

이 GET은 다른 대화를 나열하지 않고 응답 내용을 대신 공급하지도 않습니다. 정상 완료 출처는 계속 `completion_source=signed-stream-handoff-v1`입니다. Signed 완료가 없거나 현재 분기에 tool 경로가 있거나 결과가 다르면 중단합니다. Proof GET이 발생하는 빈도는 보장하지 않습니다.

## 복구와 가져오기: 답변 회수와 로컬 저장

**GET 전용 응답 복구**는 전송 허가 이후 프로세스가 중단되거나 signed 수집이 실패했을 때 명시적으로 실행합니다. 정확히 하나의 `submission_dispatching`과 최대 하나의 대응 `submission_dispatched` 기록을 요구하므로, child가 `submitted` event를 남기기 전에 중단된 경우도 포함할 수 있습니다. POST를 반복하거나 signed WebSocket을 재연결하는 기능은 아닙니다.

복구는 최근 갱신된 대화 최대 20개의 목록과 시간 조건에 맞는 후보 상세를 GET으로 확인합니다. 결정적 user message ID와 정확한 outbound 본문이 일치하는 대화 하나를 찾은 뒤 그 현재 분기의 완료된 답변을 회수합니다. 일치 후에는 해당 대화만 읽습니다. 무관한 대화 제목·본문은 출력하거나 영구 저장하지 않습니다. 대상이 최근 20개 밖으로 밀려나거나 identity·본문·완료를 증명할 수 없으면 복구가 실패할 수 있습니다.

복구 완료 출처는 `conversation-readback-v1`이며 signed 수집 성공으로 기록하지 않습니다. 답변 대기 중에는 GET 복구를 다시 실행할 수 있지만, 이미 `imported` 또는 `evaluated`인 패키지는 중복 수집을 거부합니다.

**응답 자동 가져오기**(import)는 정상 수집과 GET 복구가 공유하는 로컬 저장 단계입니다. `responses/response.raw.md`에 수집 결과 원문, `responses/response.md`에 패키지 식별용 deterministic wrapper를 저장하고 서로 다른 해시를 기록합니다. `response_captured` 뒤 `response_imported`를 남기고 응답 수 1, phase `imported`로 바꿉니다. 현재 사용자 CLI에는 별도의 수동 import 명령이 없으며 `consult` 또는 `collect-response`가 자동 수행합니다.

## 기록과 평가: 무엇을 증명하는가

**해시 체인 실행 기록**(receipt)은 `receipt.json`의 각 event에 순번, 앞 event의 해시와 현재 해시를 기록합니다. `state.json`은 현재 단계와 다음 동작 판단을, receipt는 그 단계에 도달한 경위를 담습니다. 승인·전송 경계·수집 출처·선택적 분기 검증·raw/wrapped 해시·평가를 서로 구분해 확인할 수 있습니다. 로컬 무결성 기록이며 외부 서명 인증서나 독립 네트워크 packet trace를 대신하지 않습니다.

**Codex 독립 평가**는 Pro 조언을 현재 파일과 비교하고, 중요한 주장에 대해 재현이나 적절한 테스트를 수행한 뒤 기록합니다. `record-evaluation`은 `accepted`, `partially-accepted`, `rejected`와 근거 요약을 저장합니다. 명령 자체가 테스트하거나 주장 정확성을 판정하는 것은 아닙니다. `evaluated` 상태도 commit, push, 배포, 물리 기기 검증의 증거가 아닙니다.

`status --handoff-dir …`로 패키지 상태를 확인합니다. 실패 시 `diagnostic-status`와 `--error-format json`을 사용할 수 있으며, 오류 단계·코드·전송 여부·상태·재시도 안전성은 [실패 보고 지침](references/failure-reporting.md)에 따라 구분합니다.

## 설치와 첫 사용

요구 사항은 macOS, `/Applications/ChatGPT.app`, Runner에서 로그인할 수 있는 ChatGPT Pro 계정, Node.js 22 이상, Python 3.11 이상입니다. npm 설치는 없습니다.

다음 두 설치 명령은 `codex-skills` 저장소 루트에서 실행합니다. `<skill-dir>`는 실제 설치된 Skill 디렉터리로 바꿉니다. 기존 레거시 설치에 대한 전환 증거를 installer가 요구하면 해당 진단을 해결한 뒤 업데이트합니다.

```bash
python3 scripts/manage_skills.py install gptpro --update --dry-run
python3 scripts/manage_skills.py install gptpro --update
python3 <skill-dir>/scripts/gptpro.py launcher-install --json
```

`gptpro Launcher.app`을 열거나 다음 명령으로 Runner를 시작합니다. 로그인이 필요하면 Runner UI에서 완료한 뒤 연결과 모델을 확인합니다.

```bash
python3 <skill-dir>/scripts/gptpro.py desktop-launch --json
python3 <skill-dir>/scripts/gptpro.py desktop-doctor --json
python3 <skill-dir>/scripts/gptpro.py models --json
```

Codex에는 다음처럼 요청합니다.

```text
$gptpro review 모드로 src와 tests의 현재 변경을 ChatGPT Pro와 함께 검토해주세요.
```

직접 CLI 흐름을 확인할 때는 분석할 저장소에서 범위를 지정해 준비합니다. `<package-directory>`는 `prepare`가 반환한 `handoff_dir`로 바꿉니다.

```bash
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" --mode review --include 'src/**' --include 'tests/**' \
  --task '현재 변경의 정확성과 빠진 테스트를 검토해주세요.' --json
python3 <skill-dir>/scripts/gptpro.py verify \
  --handoff-dir <package-directory> --json
```

공개 원문·파일 목록·해시·크기·모델을 검토하고 사용자가 전송과 공개 범위를 승인한 경우에만 다음을 실행합니다.

```bash
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <package-directory> \
  --confirm-transmission --confirm-disclosure --json
python3 <skill-dir>/scripts/gptpro.py consult \
  --handoff-dir <package-directory> --json
```

전송 이후 수집 실패가 있을 때만 별도 복구를 실행합니다.

```bash
python3 <skill-dir>/scripts/gptpro.py collect-response \
  --handoff-dir <package-directory> --json
```

답변을 실제로 검증한 뒤 `record-evaluation --handoff-dir … --verdict … --summary …`로 판단과 근거를 기록합니다. 상담이 끝나면 전용 Runner의 실행 여부를 보고하고, 필요할 때 사용자가 Runner 창만 닫습니다. Launcher 상태·제거 명령은 `launcher-status`, `launcher-uninstall`이며 제거는 관리 대상 Launcher만 Trash로 옮깁니다.

## 검증 기록과 현재 한계

다음은 저장소 `docs/gptpro-source-inventory.md`에 기록된 **2026-09-05의 기존 검증 결과**입니다. README를 읽거나 문서를 검증했다는 사실만으로 현재 설치본·로그인 상태에서 재실행한 결과가 되지는 않습니다.

| 증거 수준 | 기록된 결과 | 그 결과로 확인할 수 없는 것 |
| --- | --- | --- |
| 자동 테스트·구조 검사 | Python 3.14.7/3.11.15에서 각 Skill 67개·installer 18개, Node 26.7.0에서 standalone/mirror 각각 55개 테스트 통과 기록 | 로그인된 실제 서비스 동작, 모든 Desktop 버전의 호환성 |
| 로컬 설치 검증 | 당시 source·Plugin 미러·설치본의 tree SHA-256 일치, Launcher `current=true` 기록 | 이후 문서 변경까지 설치됐는지, 원격 공개·릴리스 여부 |
| 실제 정상 상담 | Desktop `26.901.31953`에서 canary, 24,117-byte 한국어 검토 응답, 수정 후 상담과 새 Codex 작업의 설치본 상담에 대해 단일 전송·signed 수집·자동 import·독립 평가 기록 | 모든 답변의 품질, 앱 내부 backend 모델 구현, 독립 packet trace |
| 실제 중단 복구 | POST가 `stream_handoff`에 도달한 뒤 소유한 Node 수집기만 종료하고, 재전송 차단 및 GET 복구·import·독립 평가 통과 기록 | signed socket reconnect나 offset resume |

현재 signed WebSocket의 **재연결·offset resume과 기존 대화의 다중 turn continuation은 구현하지 않았습니다**. Socket이 `done` 전에 끊기면 불명확한 상태로 중단하고 GET 복구를 사용합니다. 최근 20개 밖 대화의 복구, 설치 프로세스 강제 종료 시 복원, 모든 저장소 형태는 별도 제한입니다. 설치된 Skill에서 전체 Python 테스트를 실행하면 저장소 루트의 `scripts/manage_skills.py`를 기대하는 배포 테스트 하나가 실패한다는 기존 기록도 있으며, 설치된 runtime 테스트 결과와 구분해야 합니다.

Private Electron bridge, Desktop endpoint와 stream format은 공개 OpenAI API가 아닙니다. 앱 업데이트나 private 계약 변경으로 실패할 수 있습니다. Browser, Chrome, Computer Use, 수동 Send/Copy, custom App, Developer Mode, MCP, Tunnel이나 다른 모델로의 fallback은 제공하지 않습니다. 레거시 `gptpro-mcp`와 Schema 3/4/5는 현재 상담 기능이 아닙니다.

## 상세 설명과 구현 근거

- [SKILL.md](SKILL.md): 명시적 호출 범위와 Codex 실행 절차
- [사용자 매뉴얼](references/user-manual.md), [워크플로](references/workflow.md), [보안 경계](references/security.md), [Electron runtime](references/electron-runtime.md): 설정·운영·실패 조건
- [CLI](scripts/gptpro.py), [패키지 구성](runtime/gptpro_runtime/package.py), [승인](runtime/gptpro_runtime/approvals.py): 명령, 공개 범위와 승인 결속
- [Controller](runtime/gptpro_runtime/controller.py), [receipt](runtime/gptpro_runtime/receipts.py): Runner, dispatch 경계, 자동 가져오기와 평가 기록
- [대화 전송](runtime/chatgpt-desktop/conversation-client.js), [signed handoff](runtime/chatgpt-desktop/stream-handoff.js), [delta 해석](runtime/chatgpt-desktop/delta-decoder.js), [GET readback](runtime/chatgpt-desktop/conversation-readback.js): 수집·분기 검증·복구의 구분
- [Python 검증](tests/test_gptpro.py), [Desktop 프로토콜 검증](tests/test_chatgpt_desktop.test.js): 실패 주입과 프로토콜 fixture 기반 회귀 검사
