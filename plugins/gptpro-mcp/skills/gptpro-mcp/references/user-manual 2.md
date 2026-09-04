# Companion 사용자 매뉴얼

일반 사용자는 `$gptpro`만 호출합니다. Installer가 `gptpro-mcp`를 함께 설치하고 base가 exact tree hash로 위임합니다.

직접 이 Skill을 호출하는 경우는 profile, Tunnel lifecycle, audit, recovery 또는 request-correlation 진단입니다.

1. `mcp-profile-list`와 `preflight`로 safe alias/hash만 확인합니다.
2. `$gptpro`가 exact Schema 4 package를 준비·승인합니다.
3. `mcp-activate`가 exact child와 authorization을 시작합니다.
4. ChatGPT 앱의 Pro가 승인된 read-only tools로 immutable snapshot을 탐색합니다.
5. 응답 후 `mcp-stop`, audit verification, import/evaluation을 완료합니다.

ChatGPT App/Tunnel profile은 한 번 연결해 여러 local Git repository에서 재사용합니다. Repository가 바뀌면 새 package만 필요합니다.

Browser, Chrome, Web, CDP, Electron internals, write/shell/build/test/Git tools는 지원하지 않습니다.
