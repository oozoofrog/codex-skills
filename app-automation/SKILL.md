---
name: app-automation
description: baepsae 기반으로 iOS Simulator와 macOS 앱을 자동화합니다. UI 트리 분석, 탭/입력, 스크린샷·비디오, 멀티스텝 시나리오 실행이 필요할 때 사용하고 일반 앱 개발 질문에는 사용하지 않습니다.
---

# App Automation

원본 `app-automation` 플러그인을 Codex 도구 체계에 맞게 정리한 스킬입니다.

## Use references
- `references/baepsae-tools.md`
- `references/baepsae-mcp.sample.json`

## Workflow
1. 시작 전에 `doctor` 또는 `baepsae_version`으로 환경을 확인한다.
2. 대상이 **iOS Simulator**인지 **macOS 앱**인지 먼저 구분한다.
3. 인터랙션 전에는 `analyze_ui` / `query_ui`로 현재 UI 상태를 파악한다.
4. 가능하면 좌표보다 접근성 셀렉터를 우선 사용한다.
5. 반복 시나리오는 `run_steps`로 묶고, 증거는 `screenshot`, `screenshot_app`, `record_video`, `stream_video`로 남긴다.
6. MCP가 없으면 `xcrun simctl`로 설치/실행/스크린샷 같은 기본 조작만 폴백한다.

## Best practices
- 요소가 보이지 않으면 바로 좌표 탭하지 말고 UI 분석을 다시 수행한다.
- 로그인, 온보딩, 설정 이동처럼 긴 플로우는 `run_steps`를 우선 검토한다.
- macOS 자동화는 `activate_app` 또는 `get_focused_app`으로 대상 앱을 명확히 맞춘다.

## Output expectation
- 수행한 단계
- 캡처 경로 또는 결과 요약
- 실패 시 어느 단계에서 막혔는지와 재시도 전략
