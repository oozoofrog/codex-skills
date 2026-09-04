# 사용자 매뉴얼

## 처음 한 번

Node.js 22 이상, Python 3.11 이상, `/Applications/ChatGPT.app`, 로그인된 ChatGPT Pro 계정이 필요합니다. npm, custom App, Developer Mode, MCP, Tunnel, Browser 자동화는 필요하지 않습니다.

```bash
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
python3 ~/.codex/skills/gptpro/scripts/gptpro.py init --json
```

반복해서 터미널 명령을 입력하지 않으려면 사용자용 실행기를 한 번 설치합니다.

```bash
python3 <skill-dir>/scripts/gptpro.py launcher-install --json
```

설치 위치는 `~/Applications/gptpro Launcher.app`입니다. 이 앱은 ChatGPT 복사본이 아니라, 실제 `/Applications/ChatGPT.app`에서 전용 gptpro 프로필과 loopback 포트를 사용하는 두 번째 프로세스를 여는 작은 실행기입니다. 기본 ChatGPT 앱과 동시에 실행할 수 있으며 기본 앱을 종료하거나 재실행하지 않습니다.

`gptpro Launcher`를 열거나 `desktop-launch`를 실행하세요. 전용 프로필은 `~/Library/Application Support/gptpro/runner/v1/profile`, 전용 포트는 `127.0.0.1:9223`입니다. 처음 실행에서 로그인이 필요하면 Runner 창에서 한 번 로그인합니다. 실행기는 기본 앱 프로필에서 로그인 정보를 복사하지 않습니다.

상태 확인과 제거는 다음과 같습니다. 제거는 gptpro가 설치한 정확한 앱만 휴지통으로 옮깁니다.

```bash
python3 <skill-dir>/scripts/gptpro.py launcher-status --json
python3 <skill-dir>/scripts/gptpro.py launcher-uninstall --json
```

`launcher-status`의 `chatgpt_mode`는 다음 의미입니다.

- `stopped`: 전용 Runner와 9223 포트가 모두 꺼짐
- `runner_starting`: Runner 프로세스는 있으나 포트가 아직 준비되지 않음
- `runner_unverified`: Runner와 포트가 보이지만 최종 검증 전
- `runner_verified`: 전용 프로필·포트와 `desktop-doctor` 검증까지 통과
- `port_conflict`: Runner가 아닌 프로그램이 9223을 사용함
- `process_state_unknown`: 실행 중인 프로세스를 안전하게 확인하지 못함

상담을 모두 마친 뒤에는 필요할 때 전용 Runner 창만 닫으세요. 기본 ChatGPT 앱은 계속 정상 실행됩니다. gptpro는 작업 중인 대화를 보호하기 위해 어느 프로세스도 자동 종료하지 않습니다.

설치하지 않으려면 `desktop-launch`를 사용할 수 있습니다. 이 명령도 같은 전용 프로필과 9223 포트로 두 번째 프로세스를 실행합니다. `desktop-doctor`가 프로세스 인자, renderer와 bridge를 별도로 검증하므로 단순히 포트가 열렸다는 사실만으로 상담을 시작하지 않습니다.

## 사용

```text
$gptpro review 모드로 src와 tests의 현재 변경을 ChatGPT Pro와 함께 검토해주세요.
```

Codex가 작은 관련 파일 집합을 선택하고 비밀정보를 검사합니다. `outbound.md`에는 질문, 선택 코드, diff, 필요한 외부 텍스트 원문이 들어갑니다. 256 KiB를 넘으면 전송하지 않고 파일 범위를 줄입니다.

승인 후 gptpro가 exact `gpt-5-6-pro`의 일반 Chat에 한 번 보냅니다. 직접 응답 통로나 ChatGPT가 알려 준 서명된 응답 통로에서 완료된 답변을 자동 저장합니다. 해당 통로의 완료 신호가 늦거나 누락되면 같은 메시지 ID와 정확한 `outbound.md`를 가진 기존 대화를 읽기만 하여 자동 회수합니다.

Codex나 Runner가 중간에 종료되었거나 자동 회수까지 실패했다면 같은 prompt를 다시 보내지 않습니다. 다음 명령은 기존 대화를 읽기만 하는 수동 복구 수단입니다.

```bash
python3 <skill-dir>/scripts/gptpro.py collect-response \
  --handoff-dir <package-directory> --json
```

이 읽기 작업은 여러 번 실행해도 새 메시지를 만들지 않습니다. 정확한 대화를 증명할 수 없으면 중단하고 사용자에게 알려줍니다. 후속 질문은 새 package로 시작합니다.

반복 승인은 bounded standing approval로 줄일 수 있습니다. 저장소, 경로, tracked 여부, supplement label, mode, 모델, 크기, 채널 또는 만료 범위를 벗어나면 새 승인이 필요합니다.

Codex는 Pro 답변을 그대로 적용하지 않고 현재 파일과 테스트로 검증한 뒤 평가 receipt를 남깁니다. 오류 보고에는 실패 단계, 실제 관찰, 오류 코드, 전송 여부, package 상태, 재시도 가능성, 다음 한 단계가 포함됩니다.
