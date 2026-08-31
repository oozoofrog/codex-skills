# Human checkpoints

다음 visible 상태를 Codex가 안전하게 증명하지 못하면 정상적인 “사람 확인 필요” checkpoint로 멈춥니다.

- ChatGPT 앱 로그인, account 또는 workspace
- Developer Mode/App authorization
- `Chat`과 `Pro` 선택
- 의도한 app/model
- Accessibility/Computer Use permission
- CAPTCHA, MFA 또는 OS 보안 prompt
- Send 결과가 성공인지 불명확함
- response가 완료됐는지 또는 copy가 정확했는지 불명확함

사용자에게 password, MFA code, cookie, token, API key, Tunnel ID 또는 unrelated conversation 내용을 보여 달라고 요청하지 않습니다. Electron 내부나 private endpoint로 이 경계를 우회하지 않습니다.

Checkpoint는 한 번에 정확한 한 동작만 설명합니다. Send 결과가 불명확하면 기존 Chat을 보존하고 재전송하지 않습니다. 사람이 UI를 클릭했다는 사실은 package approval, exact visible user-turn hash 또는 response import receipt를 대신하지 않습니다.
