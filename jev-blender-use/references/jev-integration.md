# Jev 결정 계층

현재 API의 Choice 계약과 기존 `jev_select.py`를 재사용한다. 신규 HTTP 구현·중복 SDK·강제 `jev-start` 로드는 없다. [TypeSafe HTTP](https://docs.typesafe.ai/api), [Choice](https://docs.typesafe.ai/primitives/choice), [confidence](https://docs.typesafe.ai/confidence)를 변경 시 확인한다.

## 정확한 개입 지점

- `strategy`: direct_bpy / geometry_nodes / modifier_stack / linked_instances / asset_import / manual_mcp_operation.
- `risk`: execute / checkpoint_then_execute / safer_alternative / human_review. 선택을 Codex가 계획에 반영한다. exact guard를 통과시키는 override가 아니다.
- `completion`: accept / retry_geometry / retry_material / retry_camera / rerender / human_review. deterministic PASS 이후 남은 fuzzy requirement만 판정한다.
- 모든 단계에 `__abstain__`가 있다. missing priority, 모순된 근거, 저 confidence, service failure는 `needs_codex`이며 안전 판정이 아니다.

```sh
python3 scripts/decision.py strategy --state state.json --output prepared.json
python3 scripts/decision.py risk --state state.json --send --min-confidence 0.85 --output risk.json
python3 scripts/decision.py completion --state state.json --send --min-confidence 0.85 --output post.json
```

`0.85`는 명령 형식 예시이며 추천·보정 완료값이 아니다. `--send`에는 사용자가 허용한 전송 범위, `TYPESAFE_API_KEY`, workflow별 명시 threshold가 필요하다. 준비 단계는 통신하지 않는다. threshold는 code가 적용하고, Jev confidence는 분포 집중도이며 정답 확률·허가가 아니다. provider가 반환한 model/분포/usage를 보존한다. 선택 이유는 **제공한 후보 기준·관찰·실제 선택**으로 설명하고 Jev가 생성하지 않은 reasoning을 붙이지 않는다.

완료용 state는 `workflow.py completion-state --run-dir run --vision vision.json --output state.json`으로 만든다. Python에서 직접 구성할 때는 `workflow.evidence_state(plan, before, after, validation, vision, candidate_sha256)`를 사용한다. pre-stage는 after/validation/vision이 null이어도 된다. completion은 fresh deterministic PASS와 필요한 Vision observation을 요구한다. 대상 요약만 보내며 이미지 bytes와 로컬 image 경로는 전송하지 않는다. 기타 scene strings/custom properties/plan은 민감할 수 있으므로 전송 전 최소화한다. 64KB 초과는 분할·범위 축소한다.

`--response response.json --min-confidence ...`는 오프라인 fixture 검사용이다. `origin=fixture`로 표시되며 finalize와 live benchmark에 사용할 수 없다. 실제 API 없이 재현 가능한 구조 검증과 실제 Jev의 판단 정확도는 다르다.

Jev가 없으면 strategy/risk를 Codex가 명시적으로 결정하고 동일한 exact guard를 유지한다. completion의 fuzzy 기준은 [Vision/verdict 계약](validation-contract.md)으로 기록한다. 중요한 모호성을 단순 fallback accept로 덮지 않는다.
