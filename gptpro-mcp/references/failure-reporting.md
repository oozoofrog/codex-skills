# Failure reporting

실패나 차단 시 다음 일곱 항목을 모두 보고합니다.

1. **실패한 단계와 작업**
2. **기대한 결과와 실제 관찰**
3. **정제된 오류 코드와 설명**
4. **전송·승인·저장소 변경 여부**
5. **현재 package/Tunnel 상태**
6. **자동 재시도 가능 여부**
7. **사용자가 해야 할 다음 조치**

`--error-format json` 오류와 observation-only `diagnostic-status`를 사용합니다. 확인된 원인, 추정, 확인 불가를 구분하고 secret prepare 차단, `MCP_INTERPRETER_PATH_DRIFT`, controller lease 유실, Desktop submission 불확실, 상태 조회 자체 실패를 서로 다른 evidence로 보고합니다.

Send, activation, tool return 또는 import가 모호하면 자동 재시도는 불가입니다. 같은 prompt나 Tunnel child를 중복 생성하지 않습니다. Login/account/App/Pro/Accessibility 확인은 실패가 아니라 사람 checkpoint입니다.

보고 자체는 package, state, receipt 또는 audit에 기록하지 않습니다.
