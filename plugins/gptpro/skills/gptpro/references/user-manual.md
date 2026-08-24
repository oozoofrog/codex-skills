# gptpro 사용자 매뉴얼

`gptpro`는 Codex가 로그인된 ChatGPT Pro 일반 Chat에 계획, 질문, 리뷰, 디버깅, 아키텍처 검토를 의뢰하는 **사람 참여형 협업 Skill**입니다.

ChatGPT Pro는 조언을 제공하고, Codex는 저장소 확인, 코드 수정, 명령 실행, 테스트, Git 작업과 최종 판단을 담당합니다. Pro의 답변이 자동으로 코드에 적용되지는 않습니다.

## 목차

- [가장 짧은 사용법](#가장-짧은-사용법)
- [누가 무엇을 하나요?](#누가-무엇을-하나요)
- [설치](#설치)
- [무엇을 선택해야 하나요?](#무엇을-선택해야-하나요)
- [Schema 4 상담을 실제로 진행하는 순서](#schema-4-상담을-실제로-진행하는-순서)
- [처음 상담하는 전체 흐름](#처음-상담하는-전체-흐름)
- [다섯 가지 상담 모드](#다섯-가지-상담-모드)
- [전송 방식 이해하기](#전송-방식-이해하기)
- [승인은 무엇을 의미하나요?](#승인은-무엇을-의미하나요)
- [브라우저에서 사람이 해야 하는 일](#브라우저에서-사람이-해야-하는-일)
- [실험적 Web MCP 읽기 전용 상담](#실험적-web-mcp-읽기-전용-상담)
- [응답을 받은 뒤](#응답을-받은-뒤)
- [`.gptpro` 폴더 관리](#gptpro-폴더-관리)
- [문제가 생겼을 때](#문제가-생겼을-때)
- [보안 체크리스트](#보안-체크리스트)
- [고급 사용자용 CLI 요약](#고급-사용자용-cli-요약)

## 가장 짧은 사용법

설치가 끝났다면 먼저 일반 상담으로 시작하세요.

```text
$gptpro review 모드로 현재 변경의 정확성과 빠진 테스트를 검토해주세요.
```

Codex가 GitHub-first `auto` 경로를 준비하고, 현재 commit을 안전하게 사용할 수 없으면 승인 전에만 paste 또는 text-file 경로를 제안합니다.

ChatGPT Pro가 승인된 로컬 snapshot을 여러 번 검색하고 읽으면서 더 깊게 분석해야 한다면 `mcp-research`를 명시합니다.

```text
$gptpro review 모드로 src와 tests를 Pro가 읽어가며 분석하도록 mcp-research로 진행해주세요.
공개 범위는 필요한 파일로 최소화하고, 실제 수정은 Pro 응답을 검증한 뒤에만 해주세요.
```

`mcp-research`라는 말이 없으면 Web MCP는 자동으로 선택되지 않습니다. 처음부터 전체 repository를 공개하도록 요청하기보다 `src/**`, `tests/**`처럼 목적에 필요한 범위를 함께 말하는 편이 좋습니다.

이후 Codex가 다음을 순서대로 진행합니다.

1. 저장소에서 필요한 파일을 고릅니다.
2. 비밀정보와 제외 대상을 검사합니다.
3. Git 상태와 파일 해시를 기록한 상담 패키지를 만듭니다.
4. 실제로 외부에 공개될 내용과 범위를 보여줍니다.
5. 사용자가 **그 패키지에 한정된 전송 승인**을 하면 ChatGPT Pro에 전달합니다.
6. Pro의 답변을 가져와 현재 코드와 테스트로 다시 검증합니다.
7. 검증을 통과한 조언만 사용합니다.

사용자는 보통 Python 명령을 직접 입력할 필요가 없습니다. Codex가 명령을 실행하고, 사람이 판단해야 하는 승인과 ChatGPT 화면 조작이 필요할 때 멈춰서 안내합니다.

## 누가 무엇을 하나요?

| 주체 | 담당하는 일 | 담당하지 않는 일 |
| --- | --- | --- |
| 사용자 | 상담 목적·공개 범위 결정, package-specific 승인, 로그인·Developer Mode·앱/워크스페이스·전송 확인 | 코드와 보안 경계를 직접 분석하거나 복잡한 CLI를 조립할 필요는 없음 |
| Codex | 파일 선택, secret/exclude 검사, package·hash·receipt 생성, Tunnel 수명주기, 응답 import, 코드·테스트 기반 독립 검증 | 승인 전 전송, 계정 선택 대행, Pro 조언의 무검증 적용 |
| ChatGPT Pro | 승인된 prompt와 허용된 repository snapshot을 읽고 계획·리뷰·디버깅·설계 조언 제공 | 로컬 파일 수정, shell/build/test 실행, Git 변경, 최종 의사결정 |

가장 중요한 원칙은 **Pro는 분석 파트너이고 Codex가 실행 책임자**라는 점입니다. Pro가 “수정했다”거나 “테스트가 통과했다”고 말해도 Codex가 로컬에서 직접 확인하기 전에는 실제 완료 증거가 아닙니다.

## 설치

### 가장 쉬운 설치

Codex에 다음과 같이 요청합니다.

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

설치 후에는 **새 Codex 작업을 시작**해야 새 Skill이 안정적으로 발견됩니다.

### Plugin으로 설치

저장소 Marketplace를 한 번 등록합니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
```

그다음 Codex의 Plugins 화면에서 `Codex Skills` Marketplace를 열고 `GPT Pro Collaborator`를 설치합니다. CLI에서는 `/plugins`로 같은 화면을 열 수 있습니다.

자세한 설치 방법은 저장소의 [Plugin 설치 안내](https://github.com/oozoofrog/codex-skills/blob/main/docs/plugin-installation.md)를 참고하세요.

### 설치 확인

새 Codex 작업에서 다음처럼 물어보면 됩니다.

```text
$gptpro를 사용할 수 있는지 확인하고, 아직 전송하지 말고 준비 단계만 설명해주세요.
```

Skill이 발견되지 않으면 먼저 새 작업을 열었는지 확인합니다. 그래도 보이지 않으면 설치 위치와 Plugin 활성 상태를 Codex에 점검해 달라고 요청하세요.

## 무엇을 선택해야 하나요?

처음에는 아래 기준만 기억하면 충분합니다.

| 원하는 일 | 추천 경로 | 특징 |
| --- | --- | --- |
| 일반적인 코드 리뷰나 설계 상담 | `auto` | GitHub를 먼저 검증하고, 불가능하면 텍스트 전달로 전환합니다. |
| 공개 범위를 특정 Git commit으로 고정 | `github` | 연결된 GitHub 저장소의 검증된 commit과 선택 경로만 요청합니다. |
| GitHub App에 저장소 접근을 주고 싶지 않음 | `paste` 또는 `text-file` | 승인된 텍스트만 붙여넣거나 Markdown 파일 하나로 전달합니다. |
| Pro가 승인된 로컬 스냅샷을 필요한 만큼 읽게 함 | `mcp-read` | 실험적 고급 경로입니다. 별도 Tunnel, Developer Mode, 이중 승인이 필요합니다. |
| Pro가 저장소 구조·여러 범위·검색·diff·테스트 증거를 오가며 분석하게 함 | `mcp-research` | 실험적 읽기 전용 협업 경로입니다. Pro 결과는 Chat으로 받고, Codex context note만 별도 승인 후 ledger에 게시할 수 있습니다. |

잘 모르겠다면 `auto`를 사용하세요. `mcp-read`와 `mcp-research`는 자동으로 선택되지 않으며, 사용자가 명시적으로 요청해야 합니다.

## Schema 4 상담을 실제로 진행하는 순서

이 절은 CLI 참고서가 아니라 실제 사용자 경험의 순서입니다. 세부 명령은 Codex가 [Workflow reference](workflow.md)와 [repository research](mcp-research.md)를 따라 실행합니다.

### 준비 조건

- macOS와 Python 3.11 이상
- 검토된 공식 OpenAI `tunnel-client`
- 로그인된 ChatGPT와 해당 account/workspace의 Developer Mode
- ChatGPT에서 사용할 Schema 4 전용 MCP 앱과 Tunnel

일반 `auto`, `github`, `paste`, `text-file` 상담에는 이 준비가 필요하지 않습니다.

### 1. 목적과 최소 범위를 요청합니다

```text
$gptpro architecture 모드로 결제 모듈의 경계와 마이그레이션 위험을 mcp-research로 분석해주세요.
공개 범위는 src/payments와 tests/payments로 제한하고 실제 수정은 하지 마세요.
```

테스트 결과나 빌드 로그도 함께 검토하려면 secret이 없는 UTF-8 파일만 evidence 후보로 지정해 달라고 요청하세요. Codex는 evidence까지 package hash와 공개 상한에 포함합니다.

### 2. Codex가 package를 준비하고 검증합니다

Codex는 선택 파일, 준비 시점 Git SHA, snapshot diff, workspace map, 선택적 evidence를 고정합니다. secret/exclude 검사에서 문제가 나오거나 범위가 너무 넓으면 이 단계에서 새 package를 준비합니다.

### 3. 표시된 한 package만 승인합니다

승인 화면에서 다음 세 내용을 확인합니다.

1. ChatGPT에 보낼 정확한 `prompt.md`
2. MCP로 읽을 수 있는 최대 파일·diff·evidence 범위, 7개 read-only 도구, 호출·바이트·시간 제한
3. Pro의 결과는 visible Chat으로 받고, Codex context note는 매번 원문·bytes·hash를 다시 승인한다는 ledger 정책

한 문장으로 세 항목을 함께 승인할 수 있지만, package ID와 표시된 범위를 반드시 포함해야 합니다.

```text
새 패키지 <package-id>의 prompt.md 전송, 표시된 MCP 최대 공개 범위,
읽기 전용 analysis ledger 사용 및 지정된 ChatGPT Web workspace의 Schema 4 앱 활성화를 승인합니다.
```

### 4. Codex가 Tunnel을 점검하고 foreground로 활성화합니다

Codex는 secret을 읽지 않는 probe와 profile 검사를 먼저 수행합니다. Python/Homebrew 경로 drift처럼 사용자의 별도 판단이 필요한 변경은 자동으로 덮어쓰지 않습니다. 활성화가 성공해도 아직 prompt 전송 승인을 새로 만든 것은 아닙니다.

### 5. 사용자가 ChatGPT 화면의 신뢰 경계를 확인합니다

새 일반 `Chat`에서 원하는 Pro 모델을 선택하고, 올바른 Personal/조직 workspace와 Schema 4 전용 앱이 도구 메뉴에 연결됐는지 확인합니다. 로그인, OAuth, Developer Mode, 앱 연결 또는 전송 버튼처럼 계정 권한이 걸린 단계는 사용자가 직접 수행할 수 있습니다.

### 6. 승인된 prompt를 한 번만 보냅니다

Pro는 필요에 따라 workspace map, 여러 범위 읽기, 여러 검색어, prepared diff, evidence, analysis status를 호출합니다. 도구 호출 수와 반환된 전체 model-visible bytes는 실제 공개 예산에서 차감됩니다. 보냈는지 모호하면 자동 재전송하지 않고 먼저 화면을 확인합니다.

### 7. 추가 Codex note는 그때마다 다시 승인합니다

Pro가 추가 사실을 요청해도 package 승인을 재사용하지 않습니다. Codex가 note 원문, byte 수, SHA-256, note ID와 현재 ledger head를 보여준 뒤 사용자가 정확히 승인한 note만 게시할 수 있습니다. 이 note도 repository를 수정하지 않습니다.

### 8. 응답 완료 뒤 권한을 닫고 검증합니다

Codex는 먼저 content authorization을 deny/revoke하고, 그 package를 소유한 정확한 Tunnel child의 종료 증거를 확인합니다. 그다음 package marker가 있는 응답을 import하고 현재 코드·테스트로 조언을 독립 검증합니다. 최종 보고에서 다음 사실을 서로 구분해야 합니다.

- Pro가 실제로 호출한 도구 수와 공개된 bytes
- authorization deny/revoke 상태
- 정확한 Tunnel runtime 종료 여부
- 응답 import와 `accepted|partially-accepted|rejected` 평가
- Codex가 실제로 실행한 테스트와 아직 남은 사람 검증

## 처음 상담하는 전체 흐름

### 1. 목적을 말합니다

좋은 요청은 목적과 범위를 함께 알려줍니다.

```text
$gptpro architecture 모드로 인증 모듈 개편안을 검토해주세요.
src/auth와 tests/auth만 공개하고, 실제 수정은 아직 하지 마세요.
```

### 2. 첫 사용 환경을 준비합니다

Codex는 먼저 읽기 전용 `init` 미리보기를 실행합니다. 기본 설정은 저장소 안에 다음 경로를 사용할 계획을 보여줍니다.

```text
<repo>/.gptpro/handoffs/
```

기본 `local` 설정은 `.gptpro/`를 해당 clone의 `.git/info/exclude`에 추가합니다. 저장소의 추적 파일인 `.gitignore`는 바꾸지 않습니다.

Codex가 정확한 대상과 변경 내용을 보여준 뒤 사용자가 승인하면 설정을 적용합니다. 이미 준비되어 있으면 다시 수정하지 않습니다.

### 3. 상담 패키지를 만듭니다

패키지에는 다음과 같은 로컬 증거가 생깁니다.

- 선택된 파일 목록과 SHA-256 해시
- Git HEAD와 dirty 상태
- 제외된 파일과 제외 사유
- 비밀정보 검사 결과
- 실제 전송 대상과 전송 파일의 해시
- 승인, 전송, 응답 가져오기, 평가 상태
- 로컬 감사용 ZIP

ZIP은 기본 업로드 파일이 아닙니다. `github`, `paste`, `text-file`, `mcp-read`, `mcp-research` 모두 ZIP을 로컬 무결성·감사 자료로 사용합니다.

### 4. 공개 범위를 검토합니다

Codex가 최소한 다음 내용을 보여줘야 합니다.

- 패키지 ID
- 상담 목적과 모드
- 선택된 전송 방식
- Git SHA와 dirty 파일 요약
- 포함 파일 수와 총 바이트 수
- 외부로 나갈 정확한 경로와 해시
- 제외·보안 경고
- Web MCP라면 최대 공개 가능 파일/해시, 정확한 도구 목록, 호출·바이트 제한, 만료 시간, 앱·워크스페이스
- `mcp-research`라면 추가 evidence/diff 해시, 읽기 전용 context-note ledger 정책, Codex note의 별도 승인 정책

모르는 경로나 예상보다 넓은 범위가 있으면 승인하지 말고 범위를 줄여 새 패키지를 만들도록 요청하세요.

### 5. 그 패키지만 승인합니다

승인은 “앞으로 gptpro를 마음대로 사용해도 된다”는 뜻이 아닙니다. 화면에 표시된 패키지의 정확한 내용과 방식만 승인합니다.

### 6. ChatGPT Pro에 한 번 전송합니다

Codex는 공식 Chrome 제어 기능을 사용하거나 사람이 직접 수행할 체크리스트를 제공합니다. 로그인, MFA, CAPTCHA, 계정·워크스페이스 선택, 앱 권한, 파일 선택, 모델 선택이 필요하면 사용자가 직접 처리합니다.

전송 여부가 불분명하면 자동으로 다시 보내지 않습니다. 중복 전송을 피하기 위해 먼저 화면 상태를 확인합니다.

### 7. 답변을 가져오고 검증합니다

답변에는 패키지별 시작·끝 marker가 있어야 합니다. Codex는 다른 패키지의 답변, marker가 빠진 답변, 중복 marker가 있는 답변을 거부합니다.

가져온 답변은 곧바로 정답으로 취급하지 않습니다. 현재 파일을 다시 읽고, 필요한 테스트를 실제로 실행한 뒤 `accepted`, `partially-accepted`, `rejected` 중 하나로 기록합니다.

## 다섯 가지 상담 모드

| 모드 | 이런 때 사용하세요 | 결과의 초점 |
| --- | --- | --- |
| `plan` | 구현 전에 순서와 위험을 정하고 싶을 때 | 단계, 의존성, 위험, 검증 gate |
| `ask` | 범위가 분명한 질문 하나가 있을 때 | 저장소 근거가 있는 답과 불확실성 |
| `review` | 현재 변경이나 PR을 검토할 때 | 우선순위가 있는 결함과 빠진 테스트 |
| `debug` | 원인이 불분명한 오류를 좁힐 때 | 가설, 구분 가능한 점검, 최소 수정 |
| `architecture` | 구조나 마이그레이션 방향을 비교할 때 | 선택지, trade-off, 결정 기준 |

예시:

```text
$gptpro plan 모드로 이 기능의 구현 순서와 검증 gate를 만들어주세요.

$gptpro ask 모드로 이 캐시 무효화 규칙이 안전한지 답해주세요.

$gptpro review 모드로 이 PR의 보안 결함과 회귀 위험을 검토해주세요.

$gptpro debug 모드로 간헐적 timeout의 원인을 구분할 실험을 설계해주세요.

$gptpro architecture 모드로 현재 구조와 event-driven 구조를 비교해주세요.
```

## 전송 방식 이해하기

### `auto`: 기본 추천

`auto`는 먼저 GitHub 경로를 검증합니다. 선택한 모든 파일이 현재 HEAD와 같고 그 commit이 GitHub remote에 존재할 때만 `github`를 사용합니다.

조건이 맞지 않으면 이유를 기록하고 다음 중 하나를 선택합니다.

- 작은 텍스트: `paste`
- 큰 텍스트: `text-file`

이 전환은 **승인 전에만** 일어납니다. 승인 후에는 전송 방식을 몰래 바꾸지 않습니다.

### `github`: 고정된 원격 snapshot

ChatGPT의 GitHub 연결이 검증된 repository와 immutable commit을 읽도록 요청합니다. 실제로 보내는 로컬 파일은 `prompt.md`뿐입니다.

다음 조건이 맞지 않으면 실패합니다.

- 선택 파일이 HEAD의 내용과 같음
- commit이 선택한 github.com remote에 push되어 있음
- PR URL을 지정했다면 PR의 remote head와 SHA가 같음

응답도 어떤 repository, commit, 파일을 읽었는지 증명해야 가져올 수 있습니다.

### `paste`: 텍스트 붙여넣기

작은 구조화 Markdown 문맥을 prompt와 함께 붙여넣습니다. GitHub 저장소 권한을 주지 않아도 되지만, 승인 화면에 표시된 텍스트 전체가 ChatGPT에 공개됩니다.

### `text-file`: Markdown 파일 첨부

큰 문맥은 `context-<id>.md` 한 개로 만들고 `prompt.md`와 함께 전달합니다. OS 파일 선택 창은 사람이 직접 다뤄야 할 수 있습니다.

### `mcp-read`: 승인된 snapshot의 제한적 읽기

ZIP 자체를 업로드하지 않습니다. ChatGPT가 Secure MCP Tunnel을 통해 로컬 MCP 서버의 세 가지 읽기 전용 도구를 호출하고, 승인된 ZIP 안에서만 필요한 부분을 읽습니다.

이 경로는 설정과 운영 책임이 더 크므로 아래 전용 절을 먼저 읽으세요.

### `mcp-research`: 읽기 범위를 넓힌 분석 협업

ZIP은 여전히 업로드하지 않습니다. Pro는 승인된 snapshot의 workspace map, 여러 줄 범위, 여러 검색어, manifest에 고정된 준비 시점 Git SHA와 snapshot 사이의 diff, 명시적으로 포함한 테스트·빌드·진단 텍스트를 읽을 수 있습니다. 일곱 MCP 도구는 모두 읽기 전용이며, Pro의 finding·hypothesis·question은 보이는 Chat 응답으로 돌아옵니다.

Codex가 추가 context를 ledger에 게시하려면 note 원문, bytes, SHA-256, note ID와 현재 head를 새로 보여주고 별도 승인을 받아야 합니다. 처음 package 승인은 이후의 모든 Codex note를 미리 승인하지 않습니다. 게시 결과는 로컬 ledger 상태이며, Pro 전송·열람 증거와 구분합니다.

## 승인은 무엇을 의미하나요?

### 일반 전송 승인

`github`, `paste`, `text-file` 승인은 다음을 묶습니다.

- 정확한 패키지와 manifest
- 선택된 전송 방식
- 외부로 나가는 파일의 정확한 bytes와 hash
- GitHub라면 repository, commit, 선택 경로와 선택적 PR

파일이 바뀌거나 전송 방식이 바뀌면 기존 승인은 무효입니다.

### `mcp-read` 이중 승인

`mcp-read`는 두 가지를 함께 명시적으로 승인해야 합니다.

1. 정확한 prompt 전송
2. MCP가 읽을 수 있는 최대 파일/해시 집합, 도구 schema, 호출·바이트 제한, 앱·워크스페이스, 만료 시간

Tunnel을 활성화하는 것과 prompt를 보내는 것은 별도 단계입니다. 활성화 성공만으로 전송 승인이 되지 않습니다.

### `mcp-research` 삼중 승인과 context note별 승인

`mcp-research` package는 다음 세 항목을 함께 확인합니다.

1. 정확한 prompt 전송
2. 최대 파일·evidence·diff 공개 범위와 7개 읽기 전용 도구·예산·만료 시간
3. Pro의 결과는 visible Chat으로 받고, ledger에는 별도 승인된 Codex context note만 게시한다는 정책

그 뒤 Codex가 ledger에 게시하는 각 context note는 다시 exact-byte 승인을 받습니다. package 승인이나 “계속 진행”이라는 일반 지시는 새 note 게시 승인으로 재사용하지 않습니다. Ledger 게시 자체는 네트워크 전송이나 Pro의 실제 열람을 뜻하지 않습니다.

### 안전한 승인 문장 예시

```text
새 패키지 <package-id>의 표시된 prompt 전송과 공개 범위를 승인합니다.
```

`mcp-read`라면 다음처럼 범위를 분명히 합니다.

```text
새 패키지 <package-id>의 prompt 전송과 표시된 MCP 최대 공개 범위를 승인합니다.
```

`mcp-research`라면 다음처럼 ledger 정책까지 명시합니다.

```text
새 패키지 <package-id>의 prompt 전송, 표시된 MCP 최대 공개 범위, 읽기 전용 context-note ledger 정책을 승인합니다.
```

패키지 ID와 공개 범위가 표시되지 않은 상태에서 포괄적으로 “모두 승인”하는 방식은 피하는 편이 안전합니다.

## 브라우저에서 사람이 해야 하는 일

다음 단계는 자동화 실패가 아니라 의도된 사람 확인 지점입니다.

- ChatGPT 로그인, MFA, CAPTCHA
- Personal/조직 workspace 선택
- GitHub 또는 MCP 앱 연결과 repository scope 확인
- Chrome 권한 또는 OS 파일 선택
- 일반 Chat과 원하는 Pro 모델/추론 설정 확인
- 전송 버튼을 한 번 눌렀는지 확인
- 완성된 응답을 복사하거나 파일로 저장

화면에 모델 선택이 기대와 다르게 보이면 현재 대화 surface가 일반 `Chat`인지 확인하세요. `Work` 등 다른 surface에서는 같은 모델 제어가 보이지 않을 수 있습니다. UI는 변경될 수 있으므로 Codex는 눈에 보이는 현재 상태를 근거로 안내해야 합니다.

사람의 조작이 필요하면 Codex에 다음처럼 말할 수 있습니다.

```text
지금 제가 해야 할 단계만 체크리스트로 알려주세요.
```

Codex는 `human-handoff`의 read-only 결과를 바탕으로 정확한 경로, 기대 증거와 재시도 규칙을 알려줍니다. 사람이 “보냈다”고 말한 것만으로 receipt를 만들지 않고, 보이는 전송 결과를 확인한 후 기록합니다.

## 실험적 Web MCP 읽기 전용 상담

### 먼저 알아둘 점

이 경로는 현재 macOS와 Python 3.11 이상을 대상으로 하며, 별도로 검토한 공식 `tunnel-client`가 필요합니다. 일반 `auto`, `github`, `paste`, `text-file` 사용에는 이 요구사항이 없습니다.

OpenAI Secure MCP Tunnel은 로컬 MCP 서버를 public inbound port로 공개하는 대신, 로컬 `tunnel-client`가 OpenAI 쪽으로 outbound HTTPS 연결을 만드는 방식입니다. 공식 OpenAI 문서는 private MCP 연결과 Developer Mode 테스트에 이 경로를 안내합니다.

Developer Mode의 주체는 Chrome이 아니라 **ChatGPT 계정·워크스페이스 설정**입니다. 공식 안내의 현재 경로는 다음과 같습니다.

```text
ChatGPT → Settings → Security and login → Developer mode
```

계정 또는 workspace 정책에 따라 메뉴가 없거나 활성화가 제한될 수 있습니다.

공식 문서:

- [Developer mode and MCP connectors in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt)
- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)

### 이 경로에서 가능한 일

ChatGPT는 승인된 immutable ZIP snapshot에 대해 정확히 세 도구만 사용할 수 있습니다.

- `gptpro_package_info`: 승인된 패키지, 경로와 제한 확인
- `gptpro_repo_search`: 승인된 UTF-8 파일 안에서 제한된 literal 검색
- `gptpro_repo_read`: 승인된 파일의 제한된 줄 범위 읽기

이 세 도구는 `mcp-read` 계약입니다. `mcp-research`를 명시적으로 선택하면 다음 기능이 추가된 정확히 7개 읽기 전용 도구 계약으로 바뀝니다.

- 준비 시점 workspace map 탐색
- 한 파일의 여러 줄 범위 읽기
- 여러 literal 검색어와 안전한 include/exclude 필터
- manifest에 고정된 준비 시점 Git SHA와 snapshot 사이의 diff 읽기
- 명시적으로 포함한 테스트·빌드·진단 artifact 읽기
- 별도 승인된 Codex context note ledger 조회

Pro의 분석·질문·제안은 MCP write가 아니라 보이는 Chat 응답으로 돌아옵니다. Codex가 추가 context를 제공해야 하면 exact-byte 승인 후 로컬 ledger에 note를 게시하고, Pro가 `gptpro_analysis_status`로 읽도록 요청합니다. 이 도구의 audit는 bytes 반환만 증명하며 모델 소비는 증명하지 않습니다.

두 계약은 한 세션에서 섞이지 않으며, 다른 계약으로 바꾸려면 새 package와 새 승인이 필요합니다.

다음 기능은 제공하지 않습니다.

- 파일 수정 또는 patch 적용
- shell, build, test 실행
- Git commit, push 또는 branch 변경
- live working tree 전체 읽기
- 임의의 로컬 파일 접근

### 사용 흐름

1. 사용자가 OpenAI에서 사용할 Tunnel과 runtime key를 준비합니다.
2. ChatGPT에서 Developer Mode를 켜고 Tunnel 방식의 MCP 연결을 만듭니다.
3. Codex가 `mcp-read` 또는 `mcp-research` 패키지를 최소 파일 범위로 준비합니다.
4. 사용자가 prompt와 최대 MCP 공개 범위를 함께 승인합니다. Research라면 evidence/diff와 읽기 전용 context-note 정책도 확인합니다.
5. Codex가 secretless probe와 profile 검사를 실행합니다.
6. 사용자가 표시된 앱·workspace가 맞는지 확인합니다.
7. Codex가 `mcp-activate`를 foreground에서 실행하고 control-plane 연결을 확인합니다.
8. ChatGPT의 새 일반 Chat에서 해당 MCP 연결을 도구 메뉴에 추가합니다.
9. 승인된 prompt를 한 번 보냅니다.
10. Research 중 추가 context가 필요하면 Codex note는 exact-byte 별도 승인 후에만 ledger에 게시합니다.
11. 답변이 끝나면 Codex가 먼저 공개 권한을 deny/revoke하고 정확한 Tunnel child를 종료합니다.
12. 답변을 가져와 독립 검증하고 평가를 기록합니다.

활성화 terminal은 상담이 끝날 때까지 닫지 마세요. 다른 terminal이나 Codex controller에서 상태 확인과 종료를 수행합니다.

### key와 profile 주의사항

- Tunnel ID와 API key를 prompt, package, receipt, audit, log에 넣지 마세요.
- key는 지원되는 `env:NAME` 또는 권한 `0600`인 절대 `file:` reference로 전달합니다.
- `~/.openai-tunnel-api-key` 같은 파일의 값을 다른 파일에 복사해 저장하지 않습니다.
- Python/Homebrew 업데이트 후 interpreter 경로만 바뀌면 `mcp-profile-check`가 drift를 감지합니다.
- profile은 자동으로 수정하지 않습니다. 현재 profile hash를 검토하고 별도 승인한 뒤, interpreter-path-only refresh만 수행합니다.
- Tunnel client binary hash 일치는 실행 중 drift 방지 증거이지, publisher 서명이나 공급망 검증을 대신하지 않습니다.

### 종료 결과를 읽는 법

다음 값은 서로 다른 사실입니다.

- `authorization_denied`: 더 이상 repository content를 읽도록 허용하지 않음
- `authorization_status`: `revoked`, `faulted` 같은 실제 상태
- `revocation_receipt_recorded`: 정상 package-scoped revoke receipt가 기록됨
- `tunnel_runtime_stopped`: 정확한 child 종료 증거가 있음

`faulted`는 안전하게 접근을 막은 상태일 수 있지만 정상 revoke 성공과 같지 않습니다. control socket 응답만으로 child가 종료됐다고 판단하지도 않습니다.

더 상세한 계약과 고급 명령은 [Web MCP repository consultation](web-mcp.md), [repository research](mcp-research.md), [Workflow reference](workflow.md)를 따르세요. 이 매뉴얼의 요약을 근거로 승인 gate를 생략하거나 명령을 축약하면 안 됩니다.

## 응답을 받은 뒤

### 1. 전송을 기록합니다

Codex는 보이는 UI에서 정확히 한 번 전송된 사실을 확인한 뒤 `mark-submitted`를 기록합니다. 실패했거나 성공 여부가 모호하면 submitted로 표시하지 않습니다.

### 2. marker가 포함된 답변을 가져옵니다

ChatGPT 응답의 다음 두 줄을 포함한 전체 텍스트를 저장합니다.

```text
BEGIN_GPTPRO_RESPONSE:<package-id>
...
END_GPTPRO_RESPONSE:<package-id>
```

### 3. Codex가 조언을 검증합니다

Codex는 다음을 확인해야 합니다.

- 패키지 작성 뒤 repository가 달라지지 않았는가
- Pro가 인용한 파일과 동작이 실제 코드와 맞는가
- 제안한 수정이 사용자 요구와 repository 규칙을 따르는가
- 관련 테스트를 실제로 실행했는가
- 시뮬레이터, 실제 기기, 배포 승인처럼 별도 증거가 필요한가

### 4. 평가를 기록합니다

- `accepted`: 핵심 조언을 근거와 함께 수용
- `partially-accepted`: 일부만 수용하고 나머지는 기각
- `rejected`: 검증 결과 사용하지 않음

Pro의 답변은 테스트 성공, 실제 기기 검증, release 승인 또는 사용자 승인 그 자체가 아닙니다.

## `.gptpro` 폴더 관리

기본 구조는 다음과 같습니다.

```text
.gptpro/
└── handoffs/
    └── <package-id>/
        ├── manifest.json
        ├── prompt.md
        ├── context-....md 또는 로컬 archive
        ├── state.json
        ├── receipt.jsonl
        └── response/evaluation 자료
```

관리 원칙:

- 기본 설정에서는 `.git/info/exclude`로 현재 clone에서만 Git 추적을 피합니다.
- `.gptpro/`를 commit하지 마세요. 사용자가 특정 receipt 보존을 명시적으로 요청한 경우만 별도 검토합니다.
- 활성 Web MCP 세션이 있는 동안 package 폴더를 이동, 수정, 삭제하지 마세요.
- 완료된 package를 삭제하면 manifest, hash, receipt, 응답, 평가와 감사 근거를 잃습니다.
- 정리가 필요하면 먼저 `status` 또는 `mcp-status`로 완료·종료 상태를 확인하고, 지울 정확한 package ID를 Codex에 검토하게 하세요.
- repository 전체나 `.gptpro` 전체를 포괄적으로 삭제하는 명령보다, 검증된 완료 package 하나씩 정리하는 방식이 안전합니다.

## 문제가 생겼을 때

### `$gptpro`가 보이지 않습니다

1. 설치 후 새 Codex 작업을 열었는지 확인합니다.
2. Plugin이 활성화되어 있는지 확인합니다.
3. 설치본과 GitHub `main`이 다른지 Codex에 구조·hash 비교를 요청합니다.

### `.gptpro`가 Git 변경으로 보입니다

Codex에 `init --repo <repo>` 미리보기를 요청하세요. 기본 `local` 방식은 `.git/info/exclude`에 `.gptpro/` 규칙을 추가하며 tracked `.gitignore`를 바꾸지 않습니다. 적용 전에는 정확한 파일과 변경 내용을 반드시 검토합니다.

### secret 경고가 나옵니다

승인하지 마세요. 해당 파일을 제외하거나 더 작은 `--include`/file list로 새 패키지를 만듭니다. 실제 secret 값을 채팅에 붙여 넣어 원인을 설명하지 마세요.

### GitHub 방식이 선택되지 않습니다

선택 파일이 HEAD와 다른지, commit이 remote에 push됐는지, PR head가 일치하는지 확인합니다. GitHub를 반드시 써야 한다면 상태를 수정한 뒤 `--transport github`로 새 패키지를 만듭니다. 기존 승인을 다른 방식에 재사용하지 않습니다.

### ChatGPT에서 Developer Mode가 없습니다

Developer Mode는 ChatGPT 설정 기능이며 브라우저 설정이 아닙니다. `Settings → Security and login`을 확인하세요. 메뉴가 없다면 account 또는 workspace policy상 사용할 수 없는 경우가 있으므로 일반 browser/GitHub/text 경로를 새 패키지로 준비합니다.

### ChatGPT에서 MCP 도구가 보이지 않습니다

다음을 순서대로 확인합니다.

1. 올바른 ChatGPT account와 workspace인가
2. Developer Mode가 켜져 있는가
3. Plugins 화면에서 올바른 Tunnel 연결을 만들었는가
4. 연결에 선택한 계약의 정확한 도구가 표시되는가 (`mcp-read` 3개, `mcp-research` 7개)
5. 새 일반 Chat의 도구 메뉴에 그 연결을 추가했는가
6. foreground `mcp-activate`가 아직 실행 중이고 control-plane poll이 성공했는가

### 전송했는지 확실하지 않습니다

다시 보내지 마세요. Codex에 `submission-uncertain` 사람 체크리스트를 요청하고 현재 ChatGPT 화면에서 사용자 메시지와 생성 상태를 확인합니다. 성공이 확인되지 않으면 submitted receipt를 만들지 않습니다.

### `mcp-activate` terminal을 닫았습니다

새 activation을 바로 시작하지 마세요. Codex가 exact controller lease와 child stop evidence를 확인해야 합니다. controller가 정말 사라진 것이 증명된 경우에만 package-specific `mcp-recover` 절차를 사용합니다. process 이름을 검색해 광범위하게 kill하는 방식은 사용하지 않습니다.

### Python 업데이트 뒤 profile 오류가 납니다

`mcp-profile-check`로 먼저 원인을 분류합니다. 오직 `MCP_INTERPRETER_PATH_DRIFT`만 기존 profile의 안전한 in-place refresh 대상입니다. Tunnel, endpoint, command option 또는 Skill root가 바뀌었다면 refresh로 덮지 말고 별도의 profile 초기화가 필요합니다.

## 보안 체크리스트

상담 전에:

- [ ] 필요한 파일만 선택했는가
- [ ] secret/exclude 경고를 읽었는가
- [ ] Git SHA와 dirty 상태가 기대와 같은가
- [ ] 전송 방식과 외부로 나갈 path/hash를 확인했는가
- [ ] 승인 문장에 정확한 package ID가 있는가
- [ ] Web MCP라면 최대 파일/바이트/호출/시간 범위와 정확한 도구 목록을 확인했는가
- [ ] `mcp-research`라면 evidence/diff와 읽기 전용 context-note ledger 정책을 확인했는가

상담 중:

- [ ] 올바른 ChatGPT account, workspace, app, 일반 Chat인가
- [ ] 원하는 Pro 모델과 설정이 보이는가
- [ ] prompt를 한 번만 보냈는가
- [ ] 로그인 정보, MFA, key, cookie를 Codex나 prompt에 복사하지 않았는가
- [ ] Web MCP foreground controller가 계속 실행 중인가
- [ ] Research의 Codex context note마다 exact-byte 승인을 따로 받았는가

상담 후:

- [ ] Web MCP 권한을 deny/revoke하고 exact child 종료를 확인했는가
- [ ] package marker가 있는 정확한 응답을 가져왔는가
- [ ] Codex가 코드와 테스트로 독립 검증했는가
- [ ] 수용·부분 수용·기각 평가와 실제 증거를 기록했는가

## 고급 사용자용 CLI 요약

일반 사용자는 아래 명령을 직접 실행하지 않아도 됩니다. 자동화나 감사가 필요할 때는 실제 설치된 `<skill-dir>`을 사용하세요.

```bash
# 첫 사용: 미리보기 후 별도 승인으로 적용
python3 <skill-dir>/scripts/gptpro.py init --repo "$PWD"
python3 <skill-dir>/scripts/gptpro.py init --repo "$PWD" --apply

# 패키지 준비, 검증, 상태 확인
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode review \
  --transport auto \
  --task "Review the current change."

python3 <skill-dir>/scripts/gptpro.py verify --handoff-dir <dir>
python3 <skill-dir>/scripts/gptpro.py status --handoff-dir <dir> --json

# 화면에 표시된 package-specific 범위를 승인받은 뒤에만 실행
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <dir> \
  --approved-by user \
  --confirm-transmission

# 사람이 해야 할 단계 확인
python3 <skill-dir>/scripts/gptpro.py human-handoff \
  --handoff-dir <dir> \
  --reason manual-transport

# 응답 가져오기
python3 <skill-dir>/scripts/gptpro.py import-response \
  --handoff-dir <dir> \
  --response-file /path/to/chatgpt-response.md
```

Web MCP의 profile, activation, stop, recovery 명령과 `mcp-research` context-note 명령은 수명주기와 승인 경계를 축약하면 안 되므로 [Workflow reference](workflow.md)와 [repository research](mcp-research.md)의 authoritative sequence를 그대로 사용하세요.
