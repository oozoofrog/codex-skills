# 세션 도구와 실제 설정

2026-09-05에 확인한 Codex 기능을 기준으로 한다. 실행 환경의 최신 도구 설명과 상위 지침이 우선한다. 도구가 없으면 이름을 지어내거나 미지원 인자를 보내지 않는다.

## 기본: 현재 작업 안의 서브에이전트

`collaboration.spawn_agent`가 있으면 내부 worker/reviewer에 사용한다. 각 도구 이름은 현재 세션의 namespace에 맞춘다.

```json
{
  "task_name": "implement_validation",
  "fork_turns": "none",
  "model": "gpt-6-astra",
  "reasoning_effort": "high",
  "message": "완성한 Task/Why/Scope/Inputs/Constraints/Acceptance criteria/Relevant evidence/Expected output packet 전문"
}
```

`message`는 자기완결형 packet으로 채운다. 확인한 절대 경로를 포함하고 불필요한 대화·비밀은 제외한다. Simple은 medium, specialist는 xhigh, final reviewer는 max로 지정한다. Git Steward도 같은 생성 도구를 사용하며 조사 medium, 변경·일반 통합 high, conflict/history 난제 xhigh를 명시한다. 역할 이름은 packet에 넣고 존재하지 않는 `git_steward` 모델·전용 도구·agent_type 인자를 만들지 않는다.

현재 `collaboration.spawn_agent`는 `fork_turns: "all"` 또는 생략 시 부모 모델·effort를 상속하며 명시적 override를 허용하지 않는다. 따라서 **`fork_turns: "none"`과 명시적 모델·effort**를 기본 조합으로 쓴다. 최근 대화가 필요한 경우에만 지원되는 양의 정수 문자열을 사용한다. Reviewer는 독립성을 위해 none을 쓴다.

반환된 agent ID/canonical task name을 저장한다. 현재 collaboration 도구는 `functions.exec` 안의 `tools.*`가 아니라 각각 직접 호출한다.

- `send_message`: 실행 중 동일 과제에 보완을 전달한다. idle agent의 새 실행을 보장하지 않는다.
- `followup_task`: 동일 과제의 보완을 배정하고 idle이면 시작한다. 모델/effort 변경 도구가 아니다.
- `wait_agent`: 결과 도착을 기다린다. 결과는 mailbox로 온다. 반복 조회 대신 blocking wait를 쓰되 사용자 진행 보고를 유지하도록 간격을 조정한다.
- `list_agents`: 가용 슬롯과 상태, 보고되는 설정을 필요할 때 확인한다. 제공되지 않는 설정은 추측하지 않는다.
- `interrupt_agent`: 실행을 멈출 때 쓴다. 종료·삭제·슬롯 해제를 의미하지 않는다. 정식 close 도구가 있을 때만 사용하고 없으면 자원 제한을 알린다.

새 세션이 별도 checkout을 뜻하지 않는다. 현재 spawn 스키마에는 cwd/worktree 인자가 없으므로 Steward가 허용된 도구로 준비한 실제 worktree 절대 경로를 packet에 넣고 워커가 매번 그 디렉터리를 명시하도록 한다. 다른 스키마가 정식 격리 인자를 제공하면 해당 설명을 따른다. 분리가 불가능하면 한 worktree의 작업을 직렬화한다. 셸 기반 Git은 현재 사용 권한을 따르고, Orca 등 특정 관리 도구를 사용자가 지정했다면 해당 도구/스킬 지침을 적용한다. 서브에이전트가 없을 때 `codex exec`나 sidebar 작업으로 몰래 우회하지 않는다.

## 사용자가 별도 sidebar 작업을 명시한 경우

일반 내부 위임에는 `mcp__codex_app__create_thread`를 쓰지 않는다. 사용자가 새 독립 작업 생성을 명시한 경우에만 현재 스키마를 읽고 `model: "gpt-6-astra"`, `thinking: "high"` 같은 필드를 지정한다. 이 경로의 effort 필드는 thinking이다.

프로젝트는 `list_projects`의 실제 ID와 `isGitRepository`를 확인한다. Git 프로젝트는 기본 worktree, 비 Git은 local이며 명시적 대상 요청이 우선한다. 브랜치나 시작 상태를 추측하지 않는다. `threadId`와 준비 중인 `clientThreadId`를 구별한다. `wait_threads`로 결과를 수집하고 실제 반환값에 맞는 created-thread directive를 보고한다. sidebar 작업은 사용자가 소유하므로 내부 워커처럼 자동 archive/delete하지 않는다.

## 리더와 설정 한계

`agents/openai.yaml`에는 UI 메타데이터를 둔다. 존재하지 않는 model/effort/leader 필드를 추가해서 런타임을 설정했다고 주장하지 않는다. 전역 config, custom agent, 기존 사용자 모델 기본값을 임의로 바꾸지 않는다.

전역 config는 기본값 증거이며 현재 작업의 실행 설정 증거가 아니다. 현재 리더 설정을 읽는 수단이 있으면 사용하고, 변경이 필요하면 사용자에게 모델 선택기를 안내한다. CLI에서 새 리더를 시작하는 인자 형식은 README에 있다.

공식 API 모델 문서, 특정 CLI의 `model/list`, 현재 데스크톱 callable schema, 실제 spawn 수락 결과를 구별한다. host/client별 catalogue가 다르면 차이를 보고한다. 현재 host에서 실패한 요청을 다른 클라이언트 결과로 성공 처리하지 않는다.

## 근거

- [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills): SKILL.md, frontmatter, UI metadata, 로컬 검색 위치.
- [OpenAI Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents): 명시적 위임, 모델·effort 상속과 override, custom agent, 권한 상속.
- [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra): 모델 ID와 지원 reasoning 수준.

역할 정책은 사용자 지정값이다. 구체적 필드·fork 제약은 실행에서 제공되는 스키마가 권위다.
