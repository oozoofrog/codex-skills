# Codex 모델 역할 분담 — 원문 검토와 적용 설계

작성·공식 문서 확인: 2026-09-25. 검토 기준: `oozoofrog/codex-skills` main `6e720366830dfd4cdbb1770114bdd957fc243410` (2026-09-24 22:28:39 KST). 이 문서는 기존 검토 요청을 구현 가능한 설계와 사용 안내로 정리한 자체 작성 문서다. 외부 글 전문이나 공식 모델 런타임 사양을 대신하지 않는다.

> 2026-09-26 갱신: 팀 구성은 [Astra Team Building](../plugins/astra-team-building/README.md)으로 대체했습니다. 아래 원문 조사와 비교 평가 도구 설명의 2026-09-25 기록은 보존합니다.

## 1. 원문과 확인 범위

사용자가 제시한 원문은 [Rahul의 X 게시물](https://x.com/sairahul1/status/2102694818485096803)이다. 검색에서 확인된 제목은 **“How To Code Almost Forever for $20/Month With Codex + …”**이다. 검색 발췌는 Plus와 Codex의 Luna/Sol 이용을 다룬다는 점까지 뒷받침한다. 직접 열기는 403/접근 제한으로 실패했다. 게시물 전체, 첨부 파일, 정확한 설치 명령, 배포 저장소, 모든 모델 분류 규칙은 이번 작업에서 확인하지 못했다.

따라서 이 문서는 원문 전문·완역이 아니다. 확인하지 못한 문단을 복원하거나 저자의 주장으로 새 규칙을 만들지 않는다. 원문 링크·짧은 제목과 확인 범위를 보존하고, 아래 적용 내용은 사용자 요구와 공식 자료를 바탕으로 작성했다. “거의 무제한”이나 특정 사용량 배수·비용 절감률을 검증된 효과로 채택하지 않았다. 이전 답변의 원문 추정과 가격표도 구현의 기준으로 삼지 않았다.

## 2. 공식 자료로 확인한 핵심

[S1]은 확인일 기준 GPT-6 Luna/Sol의 제공 화면을 Work·Codex와 Chat으로 구분하고 rollout·클라이언트별 가용성 차이를 안내한다. [S2]는 local custom agent의 모델·effort 설정 우선순위와 모델별 시작 effort를 설명한다. 이 차이 때문에 Chat/Work/Codex/외부 runner에 하나의 고정 모델표나 동일한 설정 API를 적용하지 않는다.

이 저장소의 정책과 실제 실행을 구별한다. UI에서 선택한 값, spawn 요청값, runner 수락, 실제 관측 설정은 서로 다른 증거다. 공식 local CLI 문서가 특정 desktop callable이나 외부 runner에서 동일하게 구현됐다고 주장하지 않는다.

## 3. 원래 요청에서 보존할 요구사항

Codex가 개발과 검증의 주체이며 기존 Astra 메인 세션과 긴 맥락을 유지한다. 스킬이 메인 모델·provider·로그인·권한·컨텍스트 설정을 바꾸지 않는다. 특히 기존 큰 context window와 auto-compaction 임계값을 일괄 축소하지 않는다. 새 기능이 다른 코딩 에이전트, 프록시, daemon, 전역 custom agent 설치를 필요로 하지 않게 한다.

다음은 2026-09-25 요청의 기록이며, 2026-09-26 팀 교체 요청은 위 갱신과 새 스킬을 따른다. 당시에는 기존 스킬을 재사용하고 새 독립 운영 라우터를 추가하지 않았다. 단일 작업은 직접 처리하고 위임은 이익이 있을 때만 한다. 기존 Astra-only 기본값, Git Steward 역할, 한 worktree 한 writer, 완료 증거 기준을 보존한다. 비용보다 정확한 완료가 우선이며 좁은 조사와 확정된 구현만 선택적으로 분리한다.

## 4. 반영한 개선

### gptplease: 화면별 모델 후보

[모델 선택 원본](../gptplease/references/model-selection.md)을 Chat/Work 열로 나누었다. 실제 화면에 있는 모델·effort만 적용하고, 명시 조합이 없으면 보내지 않는다. Work 후보에 최신 Luna/Sol을 포함하되 Chat을 Work로 바꾸지 않는다. keep-current·recommend-only·명시 Pro·부분 명시·Standard·단일 Send와 전송 불명 상태의 읽기 복구는 유지한다. 상담 대상의 모델을 호출한 Codex의 모델로 혼동하지 않는다.

### astra-team-building: 작업에 맞춘 팀 구성

[스킬 원본](../plugins/astra-team-building/skills/astra-team-building/SKILL.md)은 Astra·Sol·Luna의 적합한 혼합 배정을 제공하며 별도 mixed-model 선언을 요구하지 않는다. [모델 정책](../plugins/astra-team-building/skills/astra-team-building/references/model-routing.md)은 공식 출발점과 역할별 조정 기준을 구별한다. 읽기 전용이라는 이유만으로 단순 모델에 어려운 판단을 맡기지 않는다.

[팀 설계](../plugins/astra-team-building/skills/astra-team-building/references/team-design.md)는 역할과 세션을 분리한다. 리더 단독부터 시작할 수 있고, 준비된 독립 과제·슬롯·격리 환경·공유 자원·통합 여력에 따라 확장·축소한다. 실제 설정은 [세션 도구](../plugins/astra-team-building/skills/astra-team-building/references/session-tools.md)로 지정하고 요청값과 관측값을 구분한다. 기존 리더의 모델·컨텍스트·권한은 보존한다.

### unreal-agent: 이미 있는 라우팅 보완

[스킬 원본](../unreal-agent/SKILL.md)의 외부 runner 경계와 명시 호출은 유지한다. Luna의 자동 출발점을 high로 정리하고 기존 low 예시는 검증되지 않은 좁은 정책임을 명시한다. 사용자가 지정한 지원 low는 유지한다. 자동 low 채택은 별도의 승인된 비교 근거가 있을 때만 한다. 이번 PR은 low/high의 실제 성능 비교 결과를 주장하지 않는다.

### session-continuity: 전체 상태를 한 곳에서 관리

[연결 지침](../session-continuity/references/orchestration.md)을 추가했다. 일반 단일 세션의 절차와 템플릿은 유지한다. `.codex/work/<task-id>.md`를 전체 작업 복구 지점으로 쓰면 오케스트레이터 상태에는 워커 배정 등 세부 정보와 참조만 남긴다. state의 정책명과 과거 worker ID가 실행 권한이나 현재 생존 증거가 되지 않게 한다.

### 변경하지 않은 경계

Codex 내부 위임 실패를 이유로 Chat/Work나 Unreal runner를 자동 호출하지 않는다. 2026-09-25 변경에서는 marketplace 항목을 추가·삭제하지 않았다. 2026-09-26에는 팀 스킬 항목을 교체했다.

## 5. 호출 예시

설치된 버전이 이 변경을 포함하는지 먼저 확인한다. PR 생성은 사용자의 로컬 설치 업데이트가 아니다.

```text
$astra-team-building으로 이 작업에 맞는 팀을 구성하고 완료해주세요.
작은 작업은 직접 처리하고 독립 과제가 준비되면 필요한 역할만 배정하세요.
```

```text
$astra-team-building으로 이번 작업의 모델·추론 수준·환경을 배정해주세요.
메인 Astra 세션과 컨텍스트 설정은 유지하세요.
좁은 코드 위치 조사는 Luna에, 명세가 확정된 구현은 Sol에 맡기되
상태 계약과 최종 판단은 메인이 담당하세요. 커밋과 푸시는 하지 마세요.
```

```text
$gptplease Work에서 이 자료를 정리하고 완료 응답을 가져와 주세요.
모델과 사고 수준은 실제 Work 선택기와 작업 난도에 맞춰 고르세요.
```

```text
$session-continuity로 현재 task를 체크포인트해주세요.
전체 완료 조건과 다음 행동은 task state에 유지하고,
오케스트레이터 state에는 워커별 정보와 참조만 남기세요.
```

## 6. 평가 절차와 도구

`single-astra`(리더 단독), `astra-only`(Astra 위임), `mixed-model`(실제 Luna/Sol 위임)을 비교해 병렬화 효과와 모델 선택 효과를 분리한다. 평가 실행은 추가 사용량을 만들 수 있으므로 별도로 요청된 실험에서만 한다. 기본 작업에서 세 arm을 자동 실행하지 않는다.

동일한 시작 커밋·입력·공통 프로젝트 지시/초기 맥락·완료 기준·환경을 유지한다. arm별 정책문은 달라야 하므로 별도 해시로 기록한다. 서로 다른 새 세션과 격리 workspace에서 같은 case/trial의 세 arm을 수행하고, 순서를 바꾸거나 반복해 초기화·캐시·숙련 효과를 살핀다. 한 입력 문서 안에서 session/workspace ID를 재사용하면 관련 비교를 제외한다. 같은 `case_id`에서 같은 arm의 정책 해시가 반복 간 달라지면 정책 버전을 섞지 않도록 해당 case 비교를 제외한다. 세 arm의 관측된 리더 모델과 effort도 일치해야 한다. 새 세션이 맥락을 자동 공유하거나 Git worktree가 미커밋 파일을 포함한다고 가정하지 않는다. 실제 스킬 버전·client·tool·memory 구성을 기록하고 동일성이 확인되지 않으면 비교를 보류한다.

도구 [model_routing_eval.py](../scripts/model_routing_eval.py)는 **이미 기록한 JSON을 검사·집계**한다. 에이전트 실행·설정 변경·증거 파일 열기·명령 실행·가격 조회·승자 선택을 하지 않는다. 요청과 관측 설정 불일치, 누락 arm, 다른 시작 조건, 실험 전체의 workspace/session 재사용, 같은 case 안의 arm별 정책 버전 혼합, arm 간 리더 설정 차이, 승인되지 않은 혼합, 전역 설정/쓰기 격리 위반, 부분 사용량은 비교 대상에서 제외하고 이유를 남긴다. 출력의 `arms.<arm>.matched_comparison`은 비교에 포함된 기록만 요약하며, `arms.<arm>.all_attempts`에는 비교에서 제외된 기록을 포함한 전체 시도 수와 PASS/FAIL/BLOCKED/NOT_RUN/INCOMPLETE 건수를 남긴다. 비용·시간·토큰 지표는 matched comparison에서만 집계하고, 관측되지 않은 값은 null로 유지한다. 기록의 진실성·런타임을 독립 인증하는 보안 도구는 아니다.

```bash
python3 scripts/model_routing_eval.py tests/model-routing/evaluation.fixture.json
python3 -m unittest discover -s scripts/tests -p 'test_model_routing*.py' -v
python3 -m unittest discover -s scripts/tests -p 'test_model_policy_contracts.py' -v
# 실제 기록을 준비한 경우에만:
python3 scripts/model_routing_eval.py /absolute/path/to/reported-runs.json
```

입력은 `schema_version: 1`, `origin: fixture|reported-live`, `runs`를 사용한다. [합성 fixture](../tests/model-routing/evaluation.fixture.json)가 입력 모양의 예제다. 한 입력 문서는 하나의 실험 경계이며 그 안에서 각 `workspace_id`와 `session_id`는 고유해야 한다. 같은 `case_id`의 같은 arm은 모든 trial에서 같은 `policy_sha256`을 사용한다. 정책을 바꾸는 후속 평가는 새 `case_id`로 분리한다. 실제 기록은 식별자·해시·설정·관측 증거 참조를 모두 실제 값으로 바꿔야 한다. `reported-live`는 작성자의 관측 기록임을 뜻하며 도구의 독립 인증을 뜻하지 않는다. 누락 지표는 `null`로 둔다. `PASS`/`FAIL`에는 검증 증거 참조가 필요하며 `BLOCKED`, `NOT_RUN`, `INCOMPLETE`도 보존한다. 출력 보고서의 `schema_version`은 2다.

`usage_scope: entire-run`은 리더·모든 워커·재시도·통합의 총합을 같은 기준으로 집계했음을 뜻한다. 토큰·credits를 자의적으로 환산하지 않는다. 비용을 모르면 null로 유지한다. wall time은 동시에 실행한 worker 시간의 합이 아니라 전체 시작부터 최종 검증까지의 경과 시간이다. 재시도·메인 수정 시간·전체 완료 비율을 함께 보며 첫 응답 시간만으로 성공을 판정하지 않는다. 부분 지표나 제외된 batch를 성공 사례로 숨기지 않는다.

[행동 시나리오](../tests/model-routing/scenarios.json)는 실제 에이전트/UI 평가용 입력과 기대 증거다. 파일 검사나 합성 fixture의 통과가 실제 모델 선택·전송·설치 노출을 검증하지 않는다. [검증 기록](model-routing-validation.md)에 정적 검사, 집계 도구 검사, 미실행 live 검증을 분리했다.

## 7. 배포와 복구

[이번 릴리스 기록](model-routing-changelog.md)에 버전별 변경을 모았고 기존 CHANGELOG 이력은 수정하지 않았다.

2026-09-25 Plugin 버전 기록: astra-orchestrator 0.2.0, gptplease 0.3.0, unreal-agent 0.1.3, session-continuity 0.1.1. 각 standalone 수정은 Plugin 미러와 동일하게 배포한다. 현재 astra-team-building은 Plugin 내부가 원본이다. 2026-09-25 검토에서는 사용자 config·인증·설치 cache를 변경하지 않았다.

현재 팀 스킬에서 모든 역할을 Astra로 제한하려면 해당 작업에 모델 제약을 명시한다. 저장소 변경의 전체 복구는 이 PR의 commit을 통상적인 review/revert 절차로 되돌린다. 로컬 스킬·Plugin 갱신과 재시작은 별도 작업이며, 이 PR로 과거 task state나 사용자의 전역 환경을 자동 변경하지 않는다.

## 출처

- [S1 — OpenAI Models](https://learn.chatgpt.com/docs/models), 확인 2026-09-25.
- [S2 — OpenAI Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), 확인 2026-09-25.
- [S3 — 사용자 제시 X 원문](https://x.com/sairahul1/status/2102694818485096803), 직접 본문 접근 제한, 제목·검색 발췌만 확인.
- [S4 — OpenAI skill-creator](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md), 기존 스킬의 간결한 본문·필요할 때 읽는 references·검증 절차를 적용.

원문 미확보와 현지 런타임 미검증은 다른 제한이다. 공개 공식 문서 확인으로 X 전문 확보나 사용자 Mac에서의 실제 성공을 대신하지 않는다.
