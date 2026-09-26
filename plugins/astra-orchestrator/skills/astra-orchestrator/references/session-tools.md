# 세션 도구와 실제 설정

Callable 예제는 2026-09-06에 확인한 호스트 스키마의 기록이다. 2026-09-25 공식 문서로 설정 우선순위를 보완했지만 이 날짜에 로컬 호스트·CLI 실행을 재검증했다는 뜻은 아니다. 실제 실행 환경의 최신 도구 설명과 상위 지침이 우선한다. 도구가 없으면 이름을 지어내거나 미지원 인자를 보내지 않는다.

## 실행 경로 선택

| 상황 | 선택과 이유 |
| --- | --- |
| 짧거나 선행 결과에 밀접한 과제 | 리더 직접 수행: 전달·통합 비용을 줄인다. |
| 현재 목표 안의 독립된 병렬 과제 | 서브에이전트: 리더가 결과를 수집하고 현재 작업에서 완료한다. |
| 사용자가 별도 작업 생성을 명시한 장기·독립 과제 | Codex 작업: 사이드바에서 사용자가 직접 열고 후속 요청을 이어갈 수 있다. |

기본 Astra-only는 기존 Astra 역할별 effort를 유지한다. 명시적으로 선택한 혼합 모델 과제는 [혼합 모델 정책](model-routing.md)에서 고른 모델·effort를 실제 인자로 지정한다. 아래 Astra literal 예제는 Astra-only 예시이지 혼합 정책의 강제값이 아니다. 별도 작업의 생성·맥락 전달·worktree 준비·결과 통합 비용을 판단한다. “세션 생성이 나을지 검토”는 생성 요청이 아니다. 일반 위임 규칙도 별도 작업 생성 권한을 대신하지 않는다.

## 설정 우선순위와 실행 전 확인

2026-09-25 [공식 Subagents 문서](https://learn.chatgpt.com/docs/agent-configuration/subagents)의 local custom agent 계약에서는 먼저 명시적 spawn 값, 해당 `[agents]` 기본값, 부모 값을 순서대로 해석하고 custom agent 파일에 지정된 `model` / `model_reasoning_effort`가 이를 덮어쓴다. 모델만 지정한 spawn/default는 해당 모델의 기본 effort를 쓸 수 있지만, **model만 지정한 custom agent 파일은 앞서 해석된 effort를 유지**한다. 서로 다른 실행 경로의 필드명을 섞지 않는다.

선택된 custom agent가 있으면 실제 파일과 적용되는 값을 확인한다. 파일의 모델·effort가 요청과 충돌하면 해당 위임을 그대로 실행하지 말고 지원되는 다른 경로 또는 사용자 지정 충돌을 처리한다. 기존 custom agent·전역 config를 몰래 수정하거나 선택을 조용히 바꾸지 않는다. custom agent 사용·설치는 필수가 아니다. `agents/openai.yaml`의 UI 메타데이터에 model/effort 필드를 넣어 런타임을 설정했다고 하지 않는다.

현재 호스트에서 이 우선순위를 확인할 수 없다면 공식 local CLI 동작을 그 호스트의 실측 사실로 확대하지 않는다. 실제 schema와 반환값으로 확인되는 범위를 기록한다. 설정 호환성이 불명확하면 해당 위임을 미확인/보류하고 가능한 독립 작업은 계속한다.

리더의 모델·provider·로그인, `model_context_window`, `model_auto_compact_token_limit`은 보존한다. 워커가 상속하는 컨텍스트·sandbox·도구 설정의 호환성을 별도로 확인한다. 숫자를 임의 축소·복제하거나 미지원 키를 새로 만들지 않는다. 충돌을 해결하려고 사용자 전역 설정을 덮어쓰지 않는다.

## 현재 작업 안의 서브에이전트

위임 이익이 있고 모델·속도 요구를 충족할 수 있으면 현재 호스트의 정식 spawn 도구를 사용한다. 확인했던 `collaboration.spawn_agent`의 예는 다음과 같다. 각 도구 이름과 필드는 현재 schema에 맞춘다.

```json
{
  "task_name": "implement_validation",
  "fork_turns": "none",
  "model": "gpt-6-astra",
  "reasoning_effort": "high",
  "message": "목표·범위·입력·권한·완료 조건을 담은 자기완결형 업무 설명"
}
```

`message`에는 확인한 절대 경로와 필요한 계약·근거를 포함하고 불필요한 대화·비밀은 제외한다. Astra Simple은 medium, specialist는 xhigh, final reviewer는 max가 기본이다. Git Steward도 같은 생성 도구를 사용하며 조사 medium, 변경·일반 통합 high, conflict/history 난제 xhigh를 명시한다. 역할은 packet에 넣고 존재하지 않는 `git_steward` 모델·전용 도구·agent_type 인자를 만들지 않는다.

9월 6일 확인한 호스트에서는 `fork_turns: "all"` 또는 생략 시 부모 모델·effort를 상속하고 명시적 override를 허용하지 않았다. 그런 schema에서는 **`fork_turns: "none"`과 명시적 모델·effort**를 사용한다. 최근 대화가 필요할 때만 실제로 지원되는 양의 정수 문자열을 사용한다. Reviewer는 독립성을 위해 none을 사용한다. 최신 host가 다른 schema를 제공하면 그 설명이 우선하며, fork 동작을 local custom agent 계약과 동일하다고 가정하지 않는다.

반환된 agent ID/canonical task name을 저장한다. 현재 namespace의 도구를 직접 호출하고 존재하지 않는 `functions.exec` / `tools.*` 래퍼를 만들지 않는다.

- `send_message`: 실행 중 같은 과제에 보완을 전달한다. idle agent의 새 실행을 보장하지 않는다.
- `followup_task`: 지원 호스트에서 같은 과제를 보완하고 idle이면 시작한다. 모델/effort 인자가 없다면 설정 변경 수단이 아니다.
- `wait_agent`: 결과 도착을 기다린다. mailbox 또는 실제 반환 채널로 수집한다. 반복 조회 대신 지원되는 blocking wait를 쓰되 사용자 진행 보고를 유지한다.
- `list_agents`: 필요할 때 슬롯·상태·보고되는 설정을 확인한다. 제공되지 않는 설정을 추측하지 않는다.
- `interrupt_agent`: 중단은 종료·삭제·슬롯 해제를 뜻하지 않는다. 정식 close 도구가 있을 때만 사용하고 없으면 자원 제한을 알린다.

새 세션이 별도 checkout을 뜻하지 않는다. spawn에 cwd/worktree 인자가 없으면 Steward가 허용된 도구로 준비한 실제 worktree 절대 경로를 packet에 넣고 워커가 매번 그 디렉터리를 명시하도록 한다. 정식 격리 인자가 제공되면 해당 설명을 따른다. 분리가 불가능하면 한 worktree의 쓰기를 직렬화한다. 셸 기반 Git은 현재 권한을 따르고 Orca 등 사용자가 관리 도구를 지정했다면 그 지침을 적용한다. 서브에이전트가 없을 때 `codex exec`, sidebar 작업, Chat/Work 상담이나 외부 runner로 몰래 우회하지 않는다.

## 사용자가 별도 sidebar 작업을 명시한 경우

일반 내부 위임에는 `mcp__codex_app__create_thread`를 쓰지 않는다. 사용자가 새 독립 작업 생성을 명시한 경우에만 현재 schema를 읽고 해당 경로의 모델과 effort 필드를 지정한다. 확인했던 경로는 `model: "gpt-6-astra"`, `thinking: "high"`를 사용했으며 effort 필드명은 thinking이다.

프로젝트는 `list_projects`의 실제 ID와 `isGitRepository`를 확인한다. Git 프로젝트는 기본 worktree, 비 Git은 local이며 명시적 대상 요청이 우선한다. 시작 상태를 지정하지 않으면 도구의 기본 브랜치에서 시작하며 `startingState`를 생략한다. 현재 미커밋 변경까지 전달한다고 가정하지 않는다. 지정된 시작 상태만 지원 인자로 전달한다. `threadId`와 준비 중인 `clientThreadId`를 구별한다. `wait_threads`로 결과를 수집하고 실제 반환값에 맞는 created-thread directive를 보고한다. 사용자 소유 sidebar 작업을 내부 워커처럼 자동 archive/delete하지 않는다.

새 prompt는 경로·입력·권한·완료 조건을 포함해 자기완결형으로 작성한다. 현재 대화를 자동 상속한다고 가정하지 않는다. 기존 작업에 새 범위를 맡기면 지원되는 `send_message_to_thread`의 실제 모델·thinking을 지정한다. 같은 과제의 보완은 기존 설정을 유지할 수 있다. `collaboration.followup_task`에 설정 인자가 없다면 변경했다고 주장하지 않고 필요한 새 에이전트 경로를 판단한다. 준비 성공은 산출물 완료가 아니며 결과와 실제 변경을 완료 조건에 대조한다.

## 리더와 설정 한계

전역 config는 기본값의 증거이지 현재 실행 설정의 증거가 아니다. 현재 리더 설정을 읽는 수단이 있으면 사용한다. 관측 불가는 unverified로 보고하며 그 이유만으로 허용된 작업 전체를 중단하지 않는다. 다른 모델임이 확인되면 Astra-only 실행이라고 주장하지 말고 지원되는 변경 경로를 안내한다. 확인된 불일치나 생성 거부는 해당 위임에만 영향을 주며 승인된 독립 작업은 계속한다. 명시된 모델·effort를 승인 없이 대체하지 않는다. CLI에서 새 리더를 수동 시작하는 안내는 README에 있다.

공식 API 모델 문서, 특정 CLI의 `model/list`, 데스크톱 callable schema와 실제 spawn 수락 결과를 구별한다. host/client별 catalogue 차이를 보고하고 현재 host의 실패를 다른 클라이언트의 성공으로 바꾸지 않는다.

## 실행 속도와 설정 보고

Standard가 기본이다. 도구가 속도 인자를 제공하면 문서화된 Standard 값을 지정한다. 인자가 없으면 지어내지 말고 제어·확인할 수 없다고 보고한다. 모델 메타데이터에 priority만 있으면 Standard 지원으로 해석하지 않는다. Standard 전용 지시를 충족할 수 없는 위임은 실행하지 않고 가능한 리더 작업을 계속한다.

생성 직후 모델·effort 요청값과 선택 이유를 짧게 보고하고 반환된 설정으로 확인할 수 있는 범위만 검증한다. 정책값(desired), 실제 요청(submitted), 실행 확인(observed)을 구별한다. 호출 수락·전역 기본값·프롬프트의 모델명만으로 실행 설정을 확인했다고 주장하지 않는다. custom agent와 상속을 반영한 관측값이 요청과 다르면 정책 불일치로 기록한다. 스킬 파일 수정은 실행 설정 전환이 아니다.

## 근거

- [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills): 스킬과 UI 메타데이터의 역할.
- [OpenAI Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents): local 설정 우선순위와 custom agent 계약, 2026-09-25 확인.
- [OpenAI Models](https://learn.chatgpt.com/docs/models): 화면·클라이언트별 모델 제공 범위, 2026-09-25 확인.

역할 정책은 저장소의 운영값이다. 구체적 callable 필드·fork 제약은 실행에서 제공되는 schema가 권위다.
