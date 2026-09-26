# 세션 도구와 실행 설정

현재 호스트가 제공한 callable schema가 우선한다. 아래는 2026-09-26 제작 호스트에서 확인한 인터페이스 예시이며 다른 CLI·앱·Work의 동일 동작을 보장하지 않는다. 역할 이름은 도구나 sandbox 권한이 아니다.

## 실행 경로

현재 목표의 내부 과제는 정식 서브에이전트 도구로 실행한다. 작은/순차 과제는 리더가 직접 한다. 사용자가 별도 Codex 작업 생성을 명시했을 때만 `create_thread` 경로를 사용한다. “팀을 구성”, “여러 세션으로 협업”만으로 사용자 소유 사이드바 작업을 생성하지 않는다.

위임 도구를 사용할 수 없으면 리더가 수행 가능한 일을 계속하고 협업 제한을 보고한다. 임의 CLI 중첩 실행·daemon·새 sidebar 작업·Chat/Work 상담·외부 runner를 내부 위임의 자동 우회로로 쓰지 않는다. 다른 실행 경로가 명시적으로 요청됐으면 그 경로의 권한·도구 계약을 따른다.

## 내부 서브에이전트

제작 호스트의 `collaboration.spawn_agent`는 다음 필드를 제공했다.

```json
{
  "task_name": "implement_parser",
  "fork_turns": "none",
  "model": "gpt-6-sol",
  "reasoning_effort": "medium",
  "message": "절대 작업 경로·입력 계약·허용 범위·완료 조건·반환 증거를 담은 자기완결형 배정"
}
```

실제 과제에 맞춘 모델·effort를 인자로 명시한다. 이 호스트에서 `fork_turns: "all"` 또는 생략은 부모 설정을 상속하며 override를 허용하지 않는다. 다른 설정에는 `"none"` 또는 schema가 허용하는 양의 정수 문자열을 쓴다. 독립 리뷰에는 `"none"`을 사용한다. 전체 대화 대신 필요한 원 요구·계약·경로·증거를 전달한다.

서브에이전트는 파일시스템을 공유한다. spawn에 cwd/worktree 필드가 없다면 [작업 환경](workspaces-and-integration.md)을 준비하고 확인한 절대 경로를 packet에 넣는다. 각 파일·명령 작업은 그 경로를 명시해야 한다. 새 worktree에 리더의 미커밋 입력이 자동으로 포함된다고 가정하지 않는다.

- `send_message`: 실행 중인 같은 과제의 보완. idle 세션을 시작한다고 가정하지 않는다.
- `followup_task`: 지원 호스트에서 idle 세션을 다시 시작. 모델·effort 필드가 없다면 설정 변경 수단이 아니다.
- `list_agents`: 필요할 때 상태·슬롯을 확인. 반환하지 않는 설정은 추정하지 않는다.
- `wait_agent`: 결과 채널과 함께 사용. 짧은 반복 조회를 피하되 진행 보고가 막히지 않는 범위로 기다린다.
- `interrupt_agent`: 과제를 멈추고 상태를 회수할 때 사용. 종료·삭제·슬롯 해제와 같지 않다. close 도구가 없으면 실제 제한 안에서 재사용 또는 직렬화한다.

반환된 ID/canonical task name을 기록하고 현재 namespace에서 직접 호출한다. 존재하지 않는 `tools.*` 래퍼나 역할 전용 도구를 만들어내지 않는다. 같은 입력의 보완은 재사용하고, 모델 변경이나 새로운 독립 관점이 필요하면 지원되는 새 실행을 선택한다.

## 별도 Codex 작업이 요청된 경우

현재 `list_projects`로 프로젝트와 Git 여부를 확인한다. Git 프로젝트는 기본 worktree, 비 Git은 local을 선택하고 사용자의 saved-project 직접 사용 요청은 보존한다. 모델 override는 **현재 도구가 허용하는 명시 사용자 요청** 범위에서만 지정한다. 내부 spawn의 skill 기반 override 권한을 `create_thread`로 옮기지 않는다.

`create_thread`의 `model`/`thinking`과 내부 spawn의 `model`/`reasoning_effort`를 혼동하지 않는다. 생성은 비동기일 수 있으므로 실제 thread ID·host·worktree 준비를 확인한다. `clientThreadId`를 thread ID로 쓰지 않는다. `wait_threads`의 cursor 기반 대기로 결과를 수집하며 완료 뒤 실제 산출물을 통합한다.

## 설정 우선순위와 관측

선택한 custom agent 설정이 있으면 실제 파일과 현재 호스트의 상속·override 계약을 확인한다. 공식 local CLI에서는 custom agent 파일의 모델·effort가 spawn/default 설정을 덮어쓸 수 있다. 이를 모든 데스크톱 실행 경로의 실측 동작으로 확대하지 않는다. 충돌하는 명시 설정은 조용히 수정·대체하지 않는다.

`agents/openai.yaml`은 UI 메타데이터다. 모델 이름을 prompt에 쓰거나 UI 메타데이터에 임의 키를 추가해 실행 설정을 바꿨다고 하지 않는다. 리더의 모델·provider·인증·`model_context_window`·`model_auto_compact_token_limit`을 유지하고, 워커에 상속되는 값의 호환성을 별도로 확인한다. 호환성 해결을 위해 전역 설정을 축소하지 않는다.

설정은 `desired`(배정), `submitted`(실제 인자), `observed`(실행 증거)를 구분한다. spawn 수락은 실행 모델·effort 확인과 다르다. 관측 필드가 없으면 `unverified`로 둔다. 설정 불일치는 보고하고 해당 모델의 성능 측정에 넣지 않는다. 속도는 사용자 지정 또는 현재 기본을 유지한다. 속도 인자가 없으면 새 키를 만들지 않으며 priority 표기만으로 Standard를 주장하지 않는다. 명시 속도 요구를 확인할 수 없는 실행은 보류한다.

근거: [OpenAI Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [OpenAI Models](https://learn.chatgpt.com/docs/models), 2026-09-26 확인. 도구 예시는 제작 호스트의 schema 기록이며 모든 역할·effort를 실제 실행했다는 증거가 아니다.
