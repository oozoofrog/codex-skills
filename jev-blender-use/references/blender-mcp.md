# Interactive Blender MCP

## 조사한 구현 — 2026-09-27

| 구현 | 연결·특징 | 적용 |
| --- | --- | --- |
| [Blender Lab 공식 MCP](https://www.blender.org/lab/mcp-server/) / [source](https://projects.blender.org/lab/blender_mcp) | Blender 5.1+, addon + 별도 MCP process, stdio/선택적 HTTP | 공개 schema 발견, 구조화된 Python result, area image |
| [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender) | addon + stdio bridge, Codex 설정 안내, 선택적 외부 asset 기능 | 기존 설치의 도구를 사용; 외부 asset/telemetry 별도 범위 |
| [webita/blender-codex-mcp](https://github.com/webita/blender-codex-mcp) | Codex용 community fork, health check | 이름으로 추정하지 않고 실제 schema 확인 |

공식 [tool 목록](https://projects.blender.org/lab/blender_mcp/src/branch/main/readme_tools.rst)과 community [server source](https://github.com/ahujasid/mcp-for-blender/blob/main/src/blender_mcp/server.py)를 기준으로 비교했다. 설치·실제 연결 성공의 증거는 별도다. 외부 코드를 복사하지 않고 최소 stdio JSON-RPC client와 공통 inspector를 구현했다.

| 기능 | 공식 | community |
| --- | --- | --- |
| 파일 상태 | `get_blendfile_summary_path_info` | `get_addon_status` + Python probe |
| scene | `get_objects_summary`, `get_object_detail_summary` | `get_scene_info(user_prompt)`, `get_object_info(object_name)` |
| Python | `execute_blender_code(code)` | `execute_blender_code(code,user_prompt)` |
| image | `get_screenshot_of_area_as_image(area_ui_type,size_limit_in_bytes)` | `get_viewport_screenshot(max_size,user_prompt)` |

공식 execution은 JSON dictionary `result`를 사용한다. community는 stdout text를 반환하므로 어댑터의 script는 `result`와 `CODEX_BLENDER_JSON:` marker를 함께 제공한다. 단순 성공 문자열·repr는 evidence로 받지 않는다. community 기본 scene info는 10개 제한이 있어 공통 `scene_state.py`로 필요한 대상만 조사한다.

공식 `*_for_cli` helper는 dirty live state를 numbered temporary `.blend`로 저장한 뒤 삭제할 수 있다. 저장본만 읽는 경로라고 가정하지 않는다. 이 패키지의 독립 CLI는 명시된 저장본만 사용한다.

## 기존 Codex 도구를 우선

이미 Codex에 연결된 MCP가 있으면 노출된 도구 schema와 실제 읽기 호출로 상태를 확인한다. 파일 상태·현재 frame·mode·camera를 확인하고 작업할 이름을 좁힌다. 큰 Python 코드 실행은 검토와 상태 전제·checkpoint를 포함한다. 현재 세션의 도구가 없다고 MCP 설치를 자동으로 시작하지 않는다.

## stdio 어댑터

이미 설치한 신뢰 가능한 서버의 실행 argv를 지정한다. shell string·credential은 넣지 않는다.

```json
{"command":["/absolute/path/to/installed-blender-mcp-server"]}
```

community 설치를 선택한 사용자는 upstream의 `codex mcp add blender -- uvx mcp-for-blender` 안내를 참고할 수 있다. official과 community가 `blender-mcp` 이름을 공유했던 이력이 있으므로 package 이름만으로 출처를 판단하지 않는다. 실제 설치한 버전/출처를 고정한다. 이 스킬은 addon·서버·전역 MCP 설정을 자동 설치하지 않는다.

```sh
python3 scripts/mcp_bridge.py discover --config mcp.json --output-dir /tmp/mcp-discover-new
python3 scripts/mcp_bridge.py inspect --config mcp.json --plan plan.json --output-dir /tmp/mcp-inspect-new
python3 scripts/mcp_bridge.py execute --config mcp.json --plan plan.json --script edit.py \
  --before /tmp/mcp-inspect-new/state.json --trusted-script \
  --checkpoint /absolute/task/checkpoints/before-edit.blend --output-dir /tmp/mcp-edit-new
python3 scripts/mcp_bridge.py capture --config mcp.json --run-dir /tmp/mcp-edit-new --output-dir /tmp/mcp-image-new
```

`inspect --plan`은 plan의 target/protected 이름을 같은 순서로 합쳐 execute와 동일한 범위·요약 한도로 조사한다. 작업 전 일반 탐색에는 `--objects Body Head` 또는 인자 없는 inspect를 사용한다. 일반 탐색 뒤 계획의 대상 범위가 바뀌었다면 `--plan`으로 다시 조사한다.

`execute --pre-decision risk.json`는 선택적 bound Jev/Codex risk receipt를 소비한다. snapshot/after/protected postguard/candidate hash를 CLI와 같은 형태로 기록하고 `workflow.py validate/finalize`에 연결한다. 현재 제공하는 어댑터는 **같은 호스트에서 실행되는 stdio 서버**를 대상으로 한다. 원격 Blender와 HTTP 서버는 Codex의 연결 도구를 직접 사용하고 파일 전달/상태 binding을 그 환경에 맞춰 구성한다.

`capture --run-dir`는 candidate 이후 live state가 바뀌지 않았는지 캡처 전후 검사하여 image receipt를 만든다. 인자가 없으면 탐색용 이미지일 뿐 candidate 완료 근거가 아니다. 실제 image block만 저장하며 Vision 관찰은 별도다.

Tool call/deadline 오류는 실패 또는 mutation 결과 불명이다. 자동 재전송하지 않는다. 서버 stdout은 newline JSON-RPC, stderr는 진단이다. 에러 envelope·추가 필수 schema·이미지 부재·너무 큰 응답을 조용히 성공으로 처리하지 않는다.

## 사용 중 연결·API 차이 대응

설치된 MCP 도구가 있으면 첫 요청에 필요한 장면 조사부터 한다. 별도 연결 시험을 먼저 수행할 필요는 없다. 도구 이름·인자가 이 어댑터와 다르면 Codex가 노출된 schema로 직접 호출하거나 좁은 adapter를 수정한다. 공식/커뮤니티 두 가지 preset만으로 Blender 기능의 사용 범위를 제한하지 않는다.

- 추가 필수 인자: schema와 도구 설명에서 값을 결정한다. 실행 권한이나 변경 범위를 뜻하는 값은 기존 요청에 맞춘다.
- mode/context 오류: 현재 mode·활성 대상·선택을 조사하고 필요한 context를 명시한다. 가능하면 `bpy.data` 직접 API를 사용한다.
- stale state: 현재 plan 범위로 다시 조사하고 사용자의 중간 편집을 반영한다. 이전 script를 그대로 재전송하지 않는다.
- 명령 제출 뒤 timeout/disconnect: 결과 불명 상태이므로 대상·checkpoint·저장본을 재조사하고 실제 남은 변경만 수행한다.
- 연결 자체가 없음: 저장본 작업은 CLI로 진행한다. 미저장 열린 장면이 필수라면 활성화할 애드온·listener 등 확인된 한 가지 장애를 해결한다.

회복 가능한 schema/context 오류는 Codex가 처리한다. 사용자의 의도나 작업 권한이 바뀌는 경우에만 확인을 요청한다.
