# gptpro-mcp

`gptpro-mcp`는 Desktop-only `$gptpro`가 사용하는 읽기 전용 저장소 companion입니다. 기본 `gptpro` 설치 시 함께 설치되므로, 일반 상담에서는 직접 호출할 필요가 없습니다.

직접 `$gptpro-mcp`를 사용하는 경우는 다음과 같습니다.

- Secure MCP Tunnel 프로필 진단
- package/authorization/audit 상태 확인
- exact Tunnel child stop/recovery
- request-correlation 같은 고급 진단
- legacy 통합 설치의 안전한 분리 전환

ChatGPT에 제공하는 도구는 저장소 map/info/read/search/diff/evidence/analysis의 읽기 전용 집합입니다. 파일 수정, shell, build/test, Git mutation, credential 접근, 임의 네트워크 fetch는 제공하지 않습니다.

## 구조

```text
Codex / $gptpro
  ├─ context 선택, 비밀 검사, package/hash/승인
  ├─ visible macOS ChatGPT app UI
  └─ exact installed gptpro-mcp
       ├─ Secure MCP Tunnel
       ├─ immutable repository snapshot
       ├─ read-only tools and audit
       └─ authorization stop/recovery
```

ChatGPT App과 Tunnel 프로필은 사용자 단위로 한 번 연결하고 여러 저장소에서 재사용합니다. 각 상담의 package만 저장소·파일·예산에 맞게 새로 만듭니다.

Browser/Chrome/Web fallback, CDP, Electron 내부 API, 자동 로그인, credential 추출은 지원하지 않습니다.

설정과 lifecycle은 [references/secure-mcp-tunnel.md](references/secure-mcp-tunnel.md), 설치 결속은 [references/component-compatibility.md](references/component-compatibility.md), 이전 설치 전환은 [references/install-transition.md](references/install-transition.md)를 참고하세요.
