# baepsae quick reference for Codex

## Environment checks
- `doctor` — host/simulator/accessibility 상태 진단
- `baepsae_version` — 서버/바이너리 버전 확인
- `list_simulators` — 사용 가능한 시뮬레이터 목록

## iOS Simulator
- 앱 관리: `install_app`, `launch_app`, `terminate_app`, `uninstall_app`, `open_url`
- UI 분석: `analyze_ui`, `query_ui`
- 인터랙션: `tap`, `tap_tab`, `type_text`, `swipe`, `scroll`, `drag_drop`, `button`, `gesture`, `touch`
- 캡처: `screenshot`, `record_video`, `stream_video`

## macOS apps
- 앱/윈도우: `list_apps`, `get_focused_app`, `activate_app`, `list_windows`
- 인터랙션: `tap`, `type_text`, `menu_action`, `right_click`, `key`, `key_combo`, `clipboard`
- 캡처: `screenshot_app`

## Repeatable workflows
- `run_steps` — 순차 시나리오 실행

## Recommended flow
1. `doctor` / `list_simulators`
2. `analyze_ui` 또는 `query_ui`
3. selector 기반 인터랙션
4. `screenshot` 또는 `record_video`
5. 길고 복잡한 플로우는 `run_steps`
