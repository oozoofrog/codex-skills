# 재현 가능한 예제

skill directory에서 `python3 examples/run_examples.py --output-dir /absolute/new-run [--blender ...]`를 실행한다. 모든 Blender 작업은 직렬이며 새 fixture만 생성한다. 초기 exact-only fixture 하나는 finalize까지 진행한다. visual requirements가 있는 결과는 실제 observer가 image를 보고 판단한 후 완료한다. Jev와 MCP는 자동 설치·호출하지 않는다.

| 예제 | 구현 | 검증/판단 |
| --- | --- | --- |
| [Simple scene](../examples/simple-scene/plan.json) | cube/plane/camera/area light, preview | 대상 존재, 실제 구도·접지·조명 관찰 |
| [Mesh optimization](../examples/mesh-optimization/plan.json) | quad sphere의 triangle budget을 계산해 non-destructive Decimate | polygon 30% 이상 감소, Head 보호 signature, before/after silhouette 관찰, 선택적 Jev completion |
| [Geometry Nodes](../examples/geometry-nodes/plan.json) | 100×200 grid points에 저해상도 tree prototype instance, realize하지 않음 | NODES modifier, depsgraph 20,000 instances; strategy Choice는 선택적 |
| [Destructive guard](../examples/jev-guard/plan.json) | shape key fixture에 modifier apply 시도 | exact guard가 Python 실행 전 refused; Jev risk는 대안 선택용이며 금지를 뒤집지 못함 |
| [Visual retry](../examples/render-loop/plan.json) | magenta material defect → 실제 관찰 → teal material만 변경 | geometry/transform/modifier unchanged, Head/Camera/Key 보호, 후속 render 관찰 |

`render-loop/failure.json`은 알려진 재질 오류를 표현한 retry 입력 예다. 실제 Vision이 파일을 봤다는 증거를 대신하지 않는다. harness의 자동 실행은 before/after render를 만들지만 자동으로 Vision/Jev 관찰을 날조하지 않는다. `benchmark.py retry` 출력의 보존 rule을 재시도 plan에 적용한다.

Jev에 strategy를 물을 때 user goal에 규모·편집 요구·렌더/게임 전달 우선순위를 포함한다. forest fixture는 이미 geometry_nodes를 선택한 deterministic 예다. 이 실행 결과만으로 Jev가 그 전략을 골랐다고 하지 않는다. 서비스가 없어도 같은 예제가 동작한다.

예제 script는 copied-snapshot 실행을 위해 self-contained이다. `scene_setup.py`는 fixture 공통 구성의 읽기 쉬운 원본이며 실제 각 script에는 필요한 구성이 포함돼 있다. 임의의 모델·원본 장면을 이 fixture 생성기로 대체하지 않는다.

forest의 첫 preview가 잔디처럼 뭉쳐 보이면 기존 candidate를 입력으로 `geometry-nodes/refine-plan.json`과 `geometry-nodes/refine.py`를 사용한다. 20,000 instance와 재질을 유지한 채 spacing·height·camera/light만 수정하고 다시 관찰한다. 파괴적 geometry 선언이 있어 checkpoint가 생성된다.
