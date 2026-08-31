# Failure reporting

실패, 진행 차단, 기대와 다른 증거가 생기면 정제된 오류와 observation-only `diagnostic-status`를 사용해 사용자의 언어로 다음 일곱 항목을 모두 보고합니다.

1. **실패한 단계와 작업**
2. **기대한 결과와 실제 관찰**
3. **정제된 오류 코드와 설명**
4. **전송·승인·저장소 변경 여부**
5. **현재 package/Tunnel 상태**
6. **자동 재시도 가능 여부**
7. **사용자가 해야 할 다음 조치**

```bash
python3 <skill-dir>/scripts/gptpro.py --error-format json diagnostic-status \
  --handoff-dir <optional-package-directory>
```

확인된 원인, 추정 원인, 확인 불가를 구분합니다. Transmission, approval, tracked worktree, local package artifact, Git metadata 변경은 각각 증거가 있을 때만 단정합니다. `diagnostic-status` 자체는 recovery, expiry commit, receipt/audit write 또는 runtime directory 생성을 수행하지 않습니다.

Desktop Send, Tunnel activation, response import 결과가 모호하면 자동 재시도는 불가입니다. 특히 prompt는 재전송하지 않습니다. 아직 생성 중인 같은 assistant response의 collection만 `collection_retry_allowed=true`일 수 있습니다.

로그인, workspace, app, model, Pro, Accessibility 확인은 실패가 아니라 “진행 중단, 사람 확인 필요”로 표현합니다. 다음 조치는 사용자 또는 Codex가 수행할 정확한 한 단계와 새 승인이 필요한지를 포함합니다.
