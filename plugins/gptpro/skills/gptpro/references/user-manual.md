# 사용자 매뉴얼

## 1. 한 번만 준비하는 것

1. macOS ChatGPT 앱에 로그인합니다.
2. ChatGPT Developer Mode에서 읽기 전용 App과 Secure MCP Tunnel을 연결합니다. 이 배포에서 ChatGPT Plugins에 보이는 App 이름은 `gptpro`입니다.
3. Codex가 ChatGPT 앱 화면을 조작할 수 있도록 요청될 때 Accessibility/Computer Use 권한을 확인합니다.
4. 저장소에서 `python3 scripts/manage_skills.py install gptpro`를 실행합니다. `gptpro-mcp`도 함께 설치됩니다.
5. Private App ID file을 사용한다면 README의 `desktop-bind`를 한 번 실행합니다.

이 App/Tunnel 연결은 여러 프로젝트에서 재사용합니다. 프로젝트마다 profile이나 app을 새로 만들지 않습니다.

이름을 구분하세요. Codex의 Skill/Plugin 목록에서는 `GPT Pro Collaborator`로 보이지만, ChatGPT 앱에서 상담에 붙이는 App은 `gptpro`로 보입니다.

## 2. 매번 하는 것

새 Codex 작업에서 다음처럼 요청합니다.

```text
$gptpro 이 변경을 리뷰하고 빠진 테스트를 찾아주세요.
```

Codex는 관련 tracked 파일만 선택하고 secret scan 후 package를 만듭니다. 처음이거나 기존 standing approval 범위를 벗어나면 정확한 공개 범위를 보여주고 승인을 요청합니다. 범위 안이면 별도 package 승인 질문을 생략할 수 있습니다.

## 3. ChatGPT 앱 단계

Codex는 ChatGPT Plugins에서 `gptpro`를 열고 “채팅에서 사용해 보기”를 선택합니다. 이때 `Work`가 열리면 `Chat`으로 바꾼 뒤 composer에 `gptpro` pill이 그대로 있는지 확인합니다. 이어서 `Pro`, workspace/model, 빈 새 general Chat을 확인하고 Prompt를 한 번만 보낸 뒤 다음 완료 응답을 복사합니다.

Login, account, Pro, app 선택이 화면상 불명확하면 사용자가 해당 한 동작만 수행합니다. Password나 token을 Codex에 제공하지 않습니다.

화면의 App 이름이 package에 기록된 이름과 다르면 전송하지 않습니다. 이름 변경은 기존 승인의 범위를 바꾸므로 실제 화면 이름으로 새 package와 승인이 필요합니다.

## 4. 답변 이후

Codex는 Tunnel을 stop/revoke하고 response를 package에 import한 뒤 현재 코드를 다시 읽어 Pro의 조언을 검증합니다. 조언이 틀리거나 오래됐으면 적용하지 않습니다.

## 5. 문제 발생 시

오류 보고에는 실패 단계, 기대/관찰, 오류 코드, 전송·승인·저장소 변경, package/Tunnel 상태, retry 가능 여부, 다음 조치가 모두 포함돼야 합니다. Send가 불명확하면 같은 prompt를 다시 보내지 않습니다.

## 6. 지원하지 않는 것

- Browser/Chrome/chatgpt.com 자동화
- GitHub나 file upload fallback
- CDP/remote-debugging
- Electron renderer/IPC/private endpoint
- ChatGPT의 local write/shell/build/test/Git 도구
- 자동 login/MFA/CAPTCHA
- 숨은 background response monitor
