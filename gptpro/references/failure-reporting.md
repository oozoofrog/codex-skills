# Failure reporting

`gptpro`가 실패하거나 사람 확인에서 멈추거나 기대한 증거를 만들지 못했을 때 Codex는 단순히 “실패했습니다”라고 끝내지 않는다. 먼저 정제된 CLI 오류와 관찰 전용 상태를 수집하고, 사용자의 대화 언어로 아래 일곱 항목을 모두 보고한다.

## 관찰 명령

예상 가능한 CLI 실패를 machine-readable 형태로 받으려면 전역 옵션을 명령 앞에 둔다.

```bash
python3 <skill-dir>/scripts/gptpro.py --error-format json verify \
  --handoff-dir <package-dir>
```

오류 JSON은 stderr에만 기록되며 `operation`, `exit_code`, 안정된 `error.code`, 정제된 `message`, `automatic_retry_allowed`, `recovery`, `sanitized`를 포함한다. 성공 stdout, manifest, receipt, MCP wire 형식은 바꾸지 않는다. 코드가 없는 정상 workflow 오류는 `GPTPRO_<COMMAND>_FAILED`, argument 오류는 `GPTPRO_ARGUMENT_ERROR`, 예상 밖 예외는 원문과 traceback 없이 `GPTPRO_INTERNAL_ERROR`가 된다.

실패 보고용 상태는 다음 명령으로만 확인한다.

```bash
python3 <skill-dir>/scripts/gptpro.py --error-format json diagnostic-status \
  --handoff-dir <optional-package-dir>
```

`diagnostic-status`는 point-in-time 관찰이다. package는 lifecycle recovery를 끈 `verify_package`로 확인하고, 기존 runtime state와 controller lease만 no-create 방식으로 읽는다. lock, runtime directory, receipt, audit footer 또는 package revision을 만들거나 고치지 않으며, 지난 TTL도 `ttl_elapsed=true`로 계산만 한다. 동시 변경을 일관되게 증명할 수 없으면 `partial` 또는 `unavailable`이라고 보고한다.

기존 `status`와 `mcp-status`는 운영 명령이다. lifecycle recovery 또는 lazy expiry를 수행할 수 있으므로, 실패 원인을 보존해야 하는 첫 진단에서 이 둘을 순수 조회로 취급하지 않는다.

## 필수 일곱 항목

다음 제목을 생략하지 않는다.

1. **실패한 단계와 작업** — CLI 명령, MCP 단계, 브라우저 단계 또는 사람 확인 지점을 구체적으로 적는다.
2. **기대한 결과와 실제 관찰** — receipt가 생겨야 했는지, 화면 확인이 필요했는지와 실제 증거를 나란히 적는다.
3. **정제된 오류 코드와 설명** — 영문 오류 코드는 그대로 두고 설명은 사용자의 언어로 쓴다. 확인된 원인, 추정, 확인 불가를 구분한다.
4. **전송·승인·저장소 변경 여부** — prompt 전송, package approval, tracked worktree, `.gptpro` 산출물, Git local metadata를 분리한다. receipt, 상태 또는 전후 Git 증거가 없으면 “확인 불가”라고 쓴다.
5. **현재 package/Tunnel 상태** — `diagnostic-status`의 availability, phase, approval, submission, recorded status, binding, lease, TTL, evidence quality를 요약한다. 다른 package의 식별정보는 노출하지 않는다.
6. **자동 재시도 가능 여부** — 오류의 `automatic_retry_allowed`를 보고하되 실제 재시도를 실행하지 않는다. 전송·승인·activation·response import 결과가 모호하면 항상 불가다.
7. **사용자가 해야 할 다음 조치** — 사용자 또는 Codex가 할 정확한 한 단계, 그리고 새 package-specific 승인이 필요한지를 적는다.

사람이 로그인, workspace, app, 모델, OAuth 또는 보이는 Send 상태를 확인해야 하는 정상 checkpoint는 “실패”가 아니라 “진행 중단, 사람 확인 필요”로 분류한다.

## retry 판정

| 관찰 | 자동 재시도 | 이유와 다음 경계 |
|---|---:|---|
| 정제된 오류가 `automatic_retry_allowed=true`이고 전송·승인·write 가능성이 없음 | 가능하다고 보고만 함 | 이번 변경은 자동 실행을 추가하지 않는다. 같은 읽기 작업을 재시도할지는 Codex가 별도로 판단한다. |
| argument/validation 오류 | 불가 | 입력 또는 package를 먼저 고친다. |
| browser Send 또는 response import 결과가 모호함 | 불가 | 기존 Chat과 receipt를 사람이 확인한다. prompt를 다시 보내지 않는다. |
| Tunnel activation 또는 audit commit 결과가 모호함 | 불가 | exact controller/lease와 package evidence를 확인한 뒤 별도 recovery 절차를 검토한다. |
| `PACKAGE_LIFECYCLE_PENDING` | 불가 | 관찰 결과를 먼저 보고한 뒤, 별도 승인·운영 단계에서 package-first recovery를 수행한다. |
| expected human checkpoint | 해당 없음 | 사용자가 표시된 한 단계를 완료할 때까지 멈춘다. |

## 상황별 최소 판정

- **secret prepare 차단**: package가 게시되지 않았다는 CLI 결과는 말할 수 있지만, tracked worktree와 Git local metadata 무변경은 별도 전후 증거가 있을 때만 말한다. secret 값은 보고하지 않는다.
- **`MCP_INTERPRETER_PATH_DRIFT` 또는 profile drift**: 기존 package approval과 profile 교체 승인은 별개다. activation/Send가 없었다는 증거를 구분하고, 별도 attended refresh 승인 전에는 자동 재시도하지 않는다.
- **controller lease 유실 또는 `NO_ACTIVE_PACKAGE`**: repository 공개 권한, package receipt, exact child 종료를 서로 다른 사실로 보고한다. activation 결과가 모호하면 새 activation을 자동 시작하지 않는다.
- **browser submission 불확실**: 화면과 submitted receipt가 일치할 때까지 전송 여부는 “확인 불가”다. 기존 Chat을 확인하며 prompt를 재전송하지 않는다.
- **상태 조회 자체 실패**: package/Tunnel 상태를 `unavailable`로 두고 정상 상태를 추정하지 않는다. 진단 명령이 수행한 mutation이 없다는 사실과 기존 repository 상태를 혼동하지 않는다.

## 안전한 보고 예시

```text
1. 실패한 단계와 작업
   verify 단계에서 package 무결성 확인이 중단됐습니다.

2. 기대한 결과와 실제 관찰
   기대: verified package와 다음 작업을 반환.
   실제: lifecycle journal이 남아 있어 observation-only 검증이 partial로 종료.

3. 정제된 오류 코드와 설명
   PACKAGE_LIFECYCLE_PENDING — package state/receipt commit이 완료되지 않았거나 recovery가 필요합니다.
   원인은 확인됐으며 journal 내용 자체는 이 보고에 노출하지 않았습니다.

4. 전송·승인·저장소 변경 여부
   prompt 전송: 확인되지 않음. 승인: 기존 기록 여부 확인 불가.
   tracked worktree 변경: 전후 Git 증거가 없어 단정하지 않음.
   diagnostic-status는 package/runtime 파일을 변경하지 않았습니다.

5. 현재 package/Tunnel 상태
   package=partial, Tunnel evidence=unavailable, mutations_performed=false.

6. 자동 재시도 가능 여부
   불가. recovery 없이 같은 명령을 반복해도 원인이 해소되지 않습니다.

7. 사용자가 해야 할 다음 조치
   Codex가 이 package에 대한 별도 lifecycle recovery 계획과 변경 범위를 먼저 제시하게 하세요.
   prompt 재전송 승인은 아직 요청하거나 재사용하지 않습니다.
```

보고문은 대화에만 반환하며 package, state, receipt 또는 audit에 저장하지 않는다.
