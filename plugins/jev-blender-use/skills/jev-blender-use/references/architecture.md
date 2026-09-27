# 구조와 계약

저장소는 루트의 standalone skill과 `plugins/<name>/skills/<name>` byte-identical mirror, `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`을 사용한다. 기존 이름 `jev-blender-use`를 유지하고 새 `skills/blender` 복사본이나 Jev SDK를 추가하지 않는다. `jev-start`는 선택적 세션 지침이며 실행 의존성이 아니다.

## 구성

| 모듈 | 책임 |
| --- | --- |
| `blender_cli.py` / `scene_worker.py` | 외부 프로세스, 입력 snapshot, 로그·시간 제한, 후보 저장 |
| `scene_state.py` | CLI/MCP 공통 bpy 수치·구조 관찰, signature |
| `scene_guard.py` | 선언한 작업의 정확한 위험 조건·checkpoint 필요성 |
| `mcp_bridge.py` | 기존 stdio 서버 initialize/tools discovery/call, live state·image 수집 |
| `workflow.py` | plan 계약, deterministic validator, completion-state/verdict 조립, evidence binding, 새 최종 파일 저장 |
| `decision.py` → `jev_select.py` | 전략/위험/완료 Choice, 기존 HTTP 전송·확률 검사 재사용 |
| `benchmark.py` | 제한된 retry 제안과 불변 attempt record |

기존 `blender_use.py`/`blender_adapter.py`의 정적 메시 GLB 경로와 `capsule_demo.py`는 별도 유지한다. 새로운 workflow가 기존 snapshot 기능에 rig/animation export를 추가한 것은 아니다.

## 선택 기준

plan/evidence 실행기는 반복 제작·보호 대상이 있는 편집·정확한 요구 조건에 적합하다. 단순 조회와 가역적인 작은 수정은 연결된 도구로 직접 수행할 수 있다. 그때도 사용자 원본과 무관한 대상을 보존하고, 실행기 밖 작업을 이 실행기의 `accepted` 기록으로 표현하지 않는다. 새 기능은 Codex가 필요한 bpy recipe를 작성해 확장한다. 미검증 환경 목록은 필수 사전 작업 목록이 아니다.

## 최소 plan

```json
{
  "schema_version": 1,
  "task_id": "body-optimization",
  "goal": "Reduce Body polygons by at least 30%; preserve Head and silhouette",
  "target_objects": ["Body"],
  "protected_objects": ["Head"],
  "operations": [{"type": "add_modifier", "target": "Body", "modifier": "DECIMATE", "ratio": 0.62}],
  "validation": [{"kind": "polygon_reduction", "object": "Body", "minimum": 0.30}],
  "visual_requirements": ["Body silhouette remains acceptable for the requested game asset"]
}
```

작업은 검토한 `script.py`로 실행한다. plan은 선언·검증 계약이며 Python을 제한하는 언어가 아니다. 선언에 없는 파괴적 행동도 수행할 수 있으므로 script 자체를 검토한다. 대상·보호 이름 겹침, 알 수 없는 operation, linked/shared data 같은 불명확한 전제는 실행 전에 반환한다. 새 기능은 좁은 작업으로 구현하고 operation/guard/검사를 함께 확장한다.

## 상태와 저장

`completed`는 health/inspect/render 작업의 완료다. `staged`는 candidate 생성이며 사용자의 작업 완료가 아니다. 정확한 검사가 실패하면 `retry`, 근거·권한·판단이 부족하면 `review`, 모든 요구가 충족되면 `accepted`와 새 최종 경로를 반환한다.

CLI run은 원본을 hash로 고정하고 `source.blend`, `plan.json`, `script.py`, `before.json`, `after.json`, `candidate.blend`, `result.json`, `trace.json`을 남긴다. 파괴적 선언에는 `checkpoint.blend`가 추가된다. 최종 저장은 이 기록의 hash를 재확인한다. 이 기록은 로컬 provenance이며 악의적인 Python·사용자 변조를 막는 서명/보안 경계가 아니다.

Jev 없는 수치 작업은 validation PASS로 finalize할 수 있다. 시각 요구가 있으면 실제 observation과 명시적 fallback verdict 또는 live Jev completion이 필요하다. 관찰자 신원과 실제 관찰 여부는 agent가 정직하게 기록해야 하며 코드가 증명하지 않는다.
