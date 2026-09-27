# 검증과 Vision evidence

## 정확한 검사

```sh
python3 scripts/workflow.py validate --plan run/plan.json --before run/before.json --after run/after.json --output validation.json
```

지원 rule:

| kind | 필드 | 의미 |
| --- | --- | --- |
| exists / absent | object | 정확한 이름 존재/부재 |
| polygon_reduction | object, minimum, evaluated(optional bool) | (before-after)/before >= minimum; 기본 evaluated |
| max_polygons / max_nonmanifold_edges / max_degenerate_faces / max_winding_conflicts | object, maximum, evaluated(optional bool) | 수치 상한 |
| unchanged | object, aspect | geometry / transform / materials / modifiers signature 비교 |
| modifier_exists | object, modifier | modifier type 존재 |
| instance_count | object, count | depsgraph evaluated instance 개수 |

보호 대상은 worker와 validator가 지원하는 raw/evaluated mesh, shape keys, vertex groups, transforms, 재질/노드, modifier/노드, parent/collection, visibility, constraints, camera/light datablock, rig 요약을 비교한다. mesh signature는 좌표·topology·UV/attribute·custom normals·weights를 포함한다. raw data는 prompt에 출력하지 않는다. signature는 이 inspector의 지원 범위이지 `.blend` 전체 의미 동등성의 증명이 아니다. action/NLA/driver의 전체 의미, 외부 image bytes, simulation cache의 모든 내용은 작업별 추가 validator가 필요하다.

인접 면의 winding conflict는 두 면이 공유 edge를 같은 방향으로 도는 경우다. nonmanifold/degenerate와 함께 문제 후보를 찾지만 모든 inward normal, 자기 교차, shading artifact를 판정하지 않는다. 의도된 열린 surface도 nonmanifold일 수 있으므로 사용자 목표에 맞게 rule을 선택한다.

검사 부재·잘린 evidence·잘못된 rule·boolean 아닌 evaluated 옵션은 실패/오류다. raw/evaluated를 섞어 감소율을 계산하지 않는다.

## Vision 관찰

preview를 실제 이미지 도구로 열고 다음 구조를 쓴다. 수치 조건을 이미지로 추정하지 않는다. 불확실한 관찰을 accept의 근거로 바꾸지 않는다.

```json
{
  "observer": "codex_vision",
  "candidate_sha256": "HASH_OF_CANDIDATE",
  "images": [{"path":"/task/render/preview.png","sha256":"IMAGE_HASH","render_metadata":"/task/render/render.json"}],
  "observations": [{"requirement":"Body silhouette remains acceptable for the requested game asset", "status":"observed", "observation":"The body remains round; a small edge facet is visible at the right shoulder."}]
}
```

각 image의 hash와 render receipt의 `source_sha256`/`preview_sha256`가 candidate에 연결돼야 한다. MCP capture의 같은-state receipt도 동일하게 사용한다. 문자열에 candidate hash를 붙이는 것만으로 다른 버전의 이미지를 재사용할 수 없다. observation은 본 사람이 기록한 관찰이며 Jev 자체의 시각 능력이나 독립 평가 증명이 아니다.

## Completion과 fallback

state는 `workflow.evidence_state(plan,before,after,validation,vision,candidate_sha256)`로 만든다. `decision.py completion`은 정확한 PASS 이후 남은 fuzzy 기준만 평가한다. Jev가 없는 경우 다음 verdict를 명시한다. `evidence_sha256`는 위 state의 `jev_select.fingerprint(state)` 값이다.

```json
{"origin":"codex","action":"accept","reason":"Observed contour differences meet the specified low-detail target.","evidence_sha256":"STATE_HASH"}
```

허용 origin은 codex/independent_codex/human이다. Codex가 관찰하고 판단한 경우 `codex`를 사용한다. 별도 evaluator가 실제로 평가했을 때만 `independent_codex`를 사용한다. 독립 검토는 필요에 따라 선택한다. 단순 exact-only 작업은 verdict 없이 검사 PASS로 마친다.

판단을 기록할 때는 해시를 직접 조립하는 대신 다음 명령을 사용한다. `--reason`에는 Codex가 실제로 내린 판단의 근거를 넣는다. 명령은 관찰을 만들거나 accept를 자동 선택하지 않으며, 현재 candidate·plan·before/after와 Vision receipt를 확인해 verdict를 연결한다.

```sh
python3 scripts/workflow.py verdict --run-dir /task/run --vision vision.json \
  --action accept --reason "Observed contour meets the requested low-detail target." \
  --output verdict.json
```

Jev completion을 사용할 때는 동일한 evidence를 다음 명령으로 조립한다.

```sh
python3 scripts/workflow.py completion-state --run-dir /task/run --vision vision.json --output state.json
python3 scripts/decision.py completion --state state.json --send --min-confidence 0.85 --output post.json
```

`completion-state`와 `verdict`는 수치 검사 PASS·후보 freshness·필요한 시각 관찰을 요구하고 새 JSON만 만든다. `0.85`는 형식 예시이며 작업에 맞는 threshold를 사용한다. 수치 검사 실패는 먼저 validate 결과를 보고 수정한다. 이미지를 아직 보지 않았거나 관찰이 uncertain이면 먼저 필요한 관찰을 마친다. exact-only 작업은 이 두 명령 없이 finalize한다.

```sh
python3 scripts/workflow.py finalize --run-dir /task/run --destination /task/final.blend \
  --vision vision.json --verdict verdict.json --output acceptance.json
# 실제 Jev 판정이 있을 때 --verdict 대신 --decision post.json
```

finalize는 후보·plan·before/after hash, 검사, 이미지와 판단 freshness를 다시 확인하고 새 경로에만 복사한다. retry/review는 파일을 publish하지 않는다. `.blend` staging 저장은 복구·검토용이며 최종 저장은 이 단계다.
