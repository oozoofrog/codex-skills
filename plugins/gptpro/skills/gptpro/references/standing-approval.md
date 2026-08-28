# 범위 제한형 상시 승인

상시 승인은 매번 새 package의 전체 manifest를 사람이 다시 승인하는 대신, 사용자가 한 번 정한 좁은 경계 안의 Schema 4 `mcp-research` package만 자동으로 exact-package 승인 상태로 전환하는 로컬 정책입니다. 기술적으로 필요한 package hash, receipt, 만료, Tunnel binding은 그대로 유지됩니다.

## 무엇을 승인하나요?

프로필은 다음 값을 고정합니다.

- 하나의 로컬 Git repository와 공개 repository identity
- `mcp-research` + browser delivery + Secure MCP Tunnel
- 검증된 Tunnel profile의 이름과 SHA-256
- ChatGPT app/workspace, 요청 모델, tool schema, protocol profile
- 허용된 상담 mode
- repository include glob, exact path, exclude glob
- dirty worktree 허용 여부
- task bytes, file count, total bytes, single-file bytes
- package approval TTL과 모든 MCP call/disclosure/session limit의 상한
- 유효기간과 승인자

외부 evidence, `--supplement`, 명시적 `--evidence-file`은 상시 승인에 포함되지 않습니다. Codex context note도 기존처럼 매 note의 정확한 bytes/hash를 별도 승인해야 합니다.

## 안전 모델

상시 승인은 package 검증을 생략하지 않습니다. 각 새 package는 secret/exclude scan, immutable archive, file/hash allowlist, Git identity, manifest hash와 receipt를 그대로 생성합니다. `approve --standing-approval <name>`은 현재 package가 프로필 범위의 부분집합인지 확인한 뒤, 그 exact manifest/file-set/Tunnel binding에 대한 일반 `approved` receipt를 기록합니다.

다음 중 하나라도 달라지면 자동 승인을 거부합니다.

- repository, current Git identity, model, app/workspace 또는 Tunnel profile
- 허용하지 않은 mode나 path
- dirty worktree를 허용하지 않았는데 package가 dirty인 경우
- task/file/MCP budget 초과
- evidence/supplement 추가
- profile 만료·철회·hash 손상·unsafe filesystem 상태
- profile과 manual confirmation flag의 혼용

프로필은 `<repo>/.gptpro/standing-approvals/<name>.json`에 mode `0600`으로 저장되고, 디렉터리는 mode `0700`입니다. 원격 저장소에는 올리지 않습니다. 파일은 secret이나 Tunnel ID를 담지 않지만, 승인 범위를 나타내는 보안 정책이므로 공유하지 마세요.

프로필은 암호학적 서명이 아니라 현재 OS 사용자 소유의 로컬 정책입니다. 같은 사용자 권한으로 실행되는 악성 프로세스까지 방어하지는 못합니다. Profile SHA-256은 우발적 변경과 receipt 결합을 검출합니다.

## 생성 절차

먼저 intended scope를 대표하는 directed Schema 4 package를 평소처럼 준비하고 exact-package 승인을 한 번 받습니다. source package는 verified local Tunnel profile을 사용해야 하며 evidence/supplement가 없어야 합니다.

```bash
python3 <skill-dir>/scripts/gptpro.py standing-approval-create \
  --repo "$PWD" \
  --handoff-dir .gptpro/handoffs/<approved-package-id> \
  --name routine-src-review \
  --approved-by user \
  --valid-for-seconds 604800 \
  --allow-mode review \
  --allow-mode debug \
  --max-task-bytes 8192 \
  --max-files 100 \
  --max-bytes 1048576 \
  --max-file-bytes 262144 \
  --dry-run
```

Codex는 dry-run JSON 전체를 사람이 이해할 수 있게 요약해야 합니다. 특히 path, mode, model/app/workspace, dirty 허용, 모든 budget, 유효기간을 보여주고 상시 승인 생성 여부를 묻습니다. 승인 후 동일 명령에서 `--dry-run`을 제거하고 `--confirm-standing-approval`을 추가합니다.

기본값은 source package의 mode, 실제 task/file 크기, 실제 file count/bytes이고 MCP limit과 package approval TTL은 source package 값을 그대로 사용합니다. 더 넓은 task/file 상한이나 mode는 생성할 때만 명시적으로 올릴 수 있습니다. 프로필 유효기간은 5분 이상 30일 이하입니다.

## 새 package에서 사용

```bash
python3 <skill-dir>/scripts/gptpro.py approve \
  --repo "$PWD" \
  --handoff-dir .gptpro/handoffs/<new-package-id> \
  --standing-approval routine-src-review
```

성공 출력과 package receipt의 `approval_source`는 `gptpro-standing-approval-v1`이며 profile name/hash/expiry와 local repository binding hash를 포함합니다. 새 package는 여전히 자체 `approval_valid_until`에 만료됩니다.

`--standing-approval`은 `--approved-by`, `--confirm-transmission`, `--confirm-mcp-disclosure`, `--confirm-analysis-ledger`와 함께 쓰지 않습니다. 자동 match가 실패하면 manual flag를 덧붙여 우회하지 말고 7항목 실패 보고 후 새 exact-package 승인 또는 더 좁은 새 profile 생성으로 진행합니다.

## 조회와 철회

```bash
python3 <skill-dir>/scripts/gptpro.py standing-approval-list --repo "$PWD"

python3 <skill-dir>/scripts/gptpro.py standing-approval-revoke \
  --repo "$PWD" \
  --name routine-src-review \
  --confirm-revocation
```

철회는 이후 package의 자동 승인을 막습니다. 이미 exact-package approval receipt가 기록된 package나 active Tunnel을 소급해 중지하지 않습니다. 이미 승인된 작업도 멈춰야 한다면 해당 package의 기존 `mcp-stop`/revoke 절차를 별도로 실행합니다.

## 브라우저와 사람 참여 경계

상시 승인은 공개 범위와 prompt 전송 권한을 미리 부여하지만 ChatGPT 로그인, Developer Mode, app/workspace 선택, OAuth, CAPTCHA, 모델 표시 불일치, 불확실한 Send 같은 UI checkpoint를 제거하지 않습니다. 명확한 visible state에서 승인된 package를 한 번 보내는 절차와 submission receipt도 유지됩니다. 전송 결과가 불확실하면 자동 재전송하지 않습니다.
