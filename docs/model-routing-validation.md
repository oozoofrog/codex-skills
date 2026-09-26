# Model routing validation — 2026-09-25

> 과거 검증 기록입니다. 아래 astra-orchestrator 명령·수치는 당시 산출물에 대한 기록이며 현재 astra-team-building의 실행 증거가 아닙니다. 현재 구조는 [새 Plugin](../plugins/astra-team-building/README.md)을 참조하세요.

## 대상과 실행 환경

기준 main: `6e720366830dfd4cdbb1770114bdd957fc243410`, Git tree `700e00e9faf1c90a74b9c527a177b23ee99bd580`. GitHub connector로 원본을 읽고 수정했습니다. 실행 컨테이너는 Linux / Python 3.13.5입니다. 네트워크 DNS 제한으로 전체 저장소 clone은 실패했으며, 아래 자동 검사는 **변경 파일 snapshot**에서 수행했습니다. 전체 저장소 테스트를 실행한 것으로 표현하지 않습니다.

기존 README, 설치 안내, 배포 테스트, session-continuity 본문 등 보존 편집 대상은 전달한 원문 바이트의 Git blob SHA를 원격 SHA와 대조한 뒤 필요한 부분만 수정했습니다. 변경 파일의 원본/미러는 byte와 mode를 대조했습니다. 나머지 파일은 GitHub의 기존 base tree를 재사용해 유지합니다. 이 절차는 사용자의 로컬 설치·인증·config 변경이 아닙니다.

## 최초 PR snapshot 검사

변경 snapshot 루트에서 실행했습니다.

```bash
python3 -m py_compile scripts/model_routing_eval.py scripts/tests/test_model_routing_eval.py scripts/tests/test_model_policy_contracts.py scripts/tests/test_plugin_distribution.py
python3 -m unittest discover -s scripts/tests -p 'test_model*.py' -v
python3 scripts/model_routing_eval.py tests/model-routing/evaluation.fixture.json
```

결과: 문법 검사 통과. 평가 집계기/CLI 20개와 정적 정책·배포 계약 8개, **총 28개 테스트 통과** (`Ran 28 tests ... OK`). 합성 fixture 출력은 `status: fixture_only`, `matched_batches: 1`, `live_model_quality_verified: false`입니다. 가격·실측 토큰 절감·실제 모델 품질의 결과가 아닙니다.

## PR #46 리뷰 재현 후속 — 2026-09-25

첨부 `pr46-review-reproductions.zip`은 패치 파일이 아니라 head `76b0a480992db5628db91be35b8a011886e70127`에 대한 네 합성 결함 재현입니다. 이를 반영해 `scripts/model_routing_eval.py`와 해당 단위 검사를 수정하고, 이 worktree에서 아래 명령을 실행했습니다.

```bash
python3 -m py_compile scripts/model_routing_eval.py scripts/tests/test_model_routing_eval.py
python3 -m unittest discover -s scripts/tests -p 'test_model*.py' -v
python3 scripts/model_routing_eval.py tests/model-routing/evaluation.fixture.json
```

문법 검사와 **32개 모델/평가 계약 테스트가 통과**했습니다. fixture CLI는 `schema_version: 2`, `status: fixture_only`, `matched_batches: 1`, `live_model_quality_verified: false`를 출력했습니다.

첨부 ZIP의 `reproduce_edge_cases.py`도 임시 디렉터리에서 현재 평가기와 테스트 fixture를 사용하도록 연결해 실행했습니다. session 재사용, arm 정책 버전 변경, 리더 effort 차이는 각각 해당 비교를 제외했고, worker 관측이 없는 BLOCKED 시도는 전체 mixed-model 시도 2건 중 1건으로 계속 집계했습니다. 해당 차단 시도의 미관측 비용은 null로 남았습니다. 이 수치는 모두 합성 재현입니다.

평가 검사는 누락 arm, 다른 시작/입력/공통 맥락/완료 기준/환경, 중복 run, 세션/workspace 재사용, 불명/불일치 모델 설정, 승인 없는 혼합, 다른 실행 경로, 불완전 사용량, null 지표, 실패/차단 보존, malformed/duplicate/nonfinite/deep JSON과 입력 크기 제한을 포함합니다. 증거 참조를 열거나 명령을 실행하지 않는 CLI 경로도 검사합니다.

정적 계약 검사는 Plugin 버전·UI 기본 문구 길이·메타데이터 정합성, 변경한 5쌍의 standalone/Plugin 파일 동일성, opt-in 정책 진입점, references 연결, 변경한 SKILL frontmatter, 17개 운영자 시나리오의 구조와 합성 fixture 표시를 검사합니다. 문장 존재 검사는 에이전트가 그 문장을 실제로 따랐다는 검증이 아닙니다.

공식 `openai/skills`의 `skills/.system/skill-creator/scripts/quick_validate.py`도 사용했습니다. 실행 전 원본 Git blob `0547b4041a5f58fa19892079a114a1df98286406`과 동일함을 확인했습니다. 별도 도구 위치를 `VALIDATOR`로 표시하면 실행한 명령은 다음과 같습니다.

```bash
python3 "$VALIDATOR" plugins/astra-orchestrator/skills/astra-orchestrator
python3 "$VALIDATOR" session-continuity
python3 "$VALIDATOR" unreal-agent
```

세 대상 모두 `Skill is valid!`입니다. 이는 최소 형식 검사이며 Plugin 설치나 런타임 지원을 보증하지 않습니다. gptplease의 SKILL.md와 상담 runtime은 수정하지 않았습니다.

검사 과정에서 테스트의 표기 비교가 `Astra-only` 대소문자 차이로 실패한 경우를 고친 뒤 전체 28개 검사를 다시 실행했습니다. 평가 CLI의 깊은 JSON에 대한 오류 처리를 보강하고 해당 입력 사례도 다시 검사했습니다.

## 미실행 / 별도 확인 필요

| 항목 | 상태와 이유 |
| --- | --- |
| 전체 `python3 -m unittest discover -s scripts/tests -v` | NOT RUN — 후속 변경 범위에 맞춰 모델/평가 계약 32개 테스트를 실행했습니다. |
| 전체 standalone/Plugin mirror 검사 | NOT RUN — 변경한 5쌍만 대조했고 나머지는 기존 tree를 유지합니다. 전체 checkout에서 `scripts/sync_skill_mirrors.py` 검사 필요. |
| `node --test gptplease/tests/*.test.mjs` | NOT RUN — 이번 변경에서 transport 코드는 그대로입니다. 전체 checkout에서 회귀 검사 필요. |
| 현재 Codex host의 실제 spawn/custom agent 우선순위/fork 지원 | NOT RUN — 공개 문서와 과거 callable 예제를 구분했고 사용자 Mac에서 실행하지 않았습니다. |
| Chat/Work의 새 모델 선택·Pro·전송/취소·응답 회수 | NOT RUN — 시나리오만 추가했고 새로운 live 상담을 전송하지 않았습니다. |
| Unreal runner의 Luna low/high 품질·사용량 비교 | NOT RUN — 별도로 승인한 실제 평가가 필요합니다. |
| task 재개와 실행 중 worker 충돌 처리 | NOT RUN — 연결 정책과 시나리오를 추가했지만 live worker를 만들지 않았습니다. |
| Plugin 설치/활성화/새 세션 노출 | NOT RUN — 사용자 로컬 cache/config를 변경하지 않았습니다. |
| X 게시물 전문 | BLOCKED — 직접 접근 제한. 제목·검색 발췌와 미확보 범위를 원문 검토 문서에 기록했습니다. |

전체 checkout에서 위 회귀 검사를 수행한 후, 새 버전의 live 동작을 주장하기 전에 [시나리오](../tests/model-routing/scenarios.json)에 실제 호스트·설정·실행 증거를 추가하세요. 평가 기록은 자동 전송·추가 요금·실험 실행의 승인이 아닙니다. 이전 릴리스의 실제 계정 관측을 이번 정책의 live 검증으로 재사용하지 않습니다.

## 검토 결론

소스/정책/문서와 오프라인 검사까지 완료했습니다. 운영에서의 혼합 모델 품질·비용 효과는 미검증입니다. 기본 Astra-only, 명시 설정, 화면/실행 경로 구분, 메인 컨텍스트, Git 권한, 한 worktree 한 writer를 보존하는 선택형 변경입니다. [설계](model-routing-review.md)와 [릴리스 기록](model-routing-changelog.md)을 함께 확인하세요.
