# Scoped retry와 benchmark

## Retry

```sh
python3 scripts/benchmark.py retry --plan plan.json --failure failure.json --attempt 1 --max-attempts 3 --output retry.json
```

```json
{"status":"retry","reason":"material_artifact","scope":"Body"}
```

출력은 수정할 facet·대상, 유지할 geometry/transform/modifier 등의 검사, 다음 attempt와 상한을 포함한다. **실행 명령이 아니라 다음 plan의 재료**다. 이전 candidate를 입력으로 쓰고 새 plan target을 좁히며 보존 대상을 `protected_objects`와 unchanged rule에 반영한다. stale source·timeout은 무조건 같은 script 재실행으로 바꾸지 않는다. budget 도달은 review다.

## 불변 run record

```sh
python3 scripts/benchmark.py record --task examples/task.json --variant codex_validation \
  --artifacts artifacts.json --status accepted --output benchmark-attempt-01.json
```

artifacts는 이름→파일 경로 mapping이다. plan/before/after/validation/trace/candidate가 필요하다. initial_scene/render/vision/pre_decision/post_decision/final_acceptance도 해당 run에 포함한다. human verdict는 선택 사항이다. 모든 참조에 SHA256을 남기고 기존 record를 덮어쓰지 않는다.

variant는 `codex_only`, `codex_validation`, `codex_jev`, `codex_jev_vision`. label만 바꿔 같은 run을 비교 실험으로 주장하지 않는다. 실제 사용한 개입과 비용·시간을 함께 기록한다. Jev variant에는 live response를 받은 pre/post decision이 필요하며 missing-key/mock/prepared 결과는 live 판정으로 집계하지 않는다. Vision variant에는 image/render receipt와 observation이 추가로 필요하다. 기본 안전 guard는 어떤 실험에서도 제거하지 않는다.

현재 taxonomy: object rename/transform, material replacement, mesh simplification, UV/normal repair, camera composition, lighting, modifier optimization, Geometry Nodes, armature repair, game asset, procedural scene, render configuration, scene cleanup. task_id/category/initial_scene/criteria를 가진 사례를 늘려 50–100개 corpus로 확장할 수 있다. 지원하지 않는 수치 검사·asset 의존성은 task별 validator를 추가한다.

이 harness는 기록·재현·provenance 기반이며 Codex/Jev의 품질 향상을 이미 측정한 benchmark 결과가 아니다. 난이도·초기 scene·예산·평가자를 통제하고 실패/기권까지 분모에 포함해야 비교가 의미 있다.
