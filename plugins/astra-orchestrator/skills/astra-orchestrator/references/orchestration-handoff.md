# session-continuity와 함께 작업 인계

기존 task state가 있거나 사용자가 두 스킬을 함께 쓰도록 요청한 장기 작업에서만 적용한다. 이 문서를 읽었다고 다른 스킬을 설치·호출하거나 AGENTS.md를 초기화하지 않는다.

## 하나의 전체 작업 복구 지점

`.codex/work/<task-id>.md`가 이미 전체 작업을 관리하면 목표·완료 조건·확정 결정·전체 검증·Exact Next Action은 그곳에 유지한다. `work/astra-orchestrator/STATE.md`는 해당 task 경로와 worker별 범위·worktree·의존성·반환 증거만 기록한다. 다른 task의 STATE가 있다면 덮어쓰지 말고 task별로 분리하거나 기존 task state 안에서 관리한다.

오케스트레이터 단독 작업은 기존 STATE만 써도 된다. 두 파일이 있으면 작성 시각만으로 정본을 고르지 않는다. 원래 사용자 목표와 실제 Git/코드/검증에 대조해 복구 지점을 정하고 상대 문서에는 참조만 남긴다. 사용자 요구를 현재 코드에 맞춰 낮추지 않는다.

## 필요한 인계 정보

정책(`astra-only` 또는 명시적으로 선택한 `mixed-model`), 적용한 사용자 요청의 짧은 참조, 변경 소유권, 실제 worktree·branch·HEAD, worker 식별자와 마지막 관측 상태, 설정의 requested/observed 구분, 검증 증거 위치와 다음 행동을 기존 항목에 짧게 기록한다. `.codex/work` 템플릿에 새 필수 필드나 긴 로그를 추가하지 않는다. 비밀·전체 대화·인증 정보를 저장하지 않는다.

재개 시 이전 worker ID의 생존, 슬롯, 작업 디렉터리, 미커밋 변경, 모델·effort를 다시 확인한다. 과거 상태를 현재 실행 증거로 사용하지 않는다. 접근 불가 worker는 `unknown`으로 두고 충돌 여부를 해결한 뒤 새 과제를 배정한다. 다른 clone/worktree에 ignored state나 미커밋 파일이 전달됐다고 가정하지 않는다.

이전 혼합 정책은 현재 지시와 원래 사용자 선택이 해당 task에 여전히 적용될 때만 유지한다. 근거가 없으면 새 혼합 위임을 시작하지 않고 가능한 리더 작업을 계속한다. 자동 세션 생성, compaction 탐지, 자동 commit·stash·reset·삭제·push는 추가하지 않는다.

완료는 전체 완료 조건과 실제 검증으로 판단한다. worker 완료와 Git 통합만으로 전체 state를 complete로 바꾸지 않는다. durable 문서 승격과 state 정리에는 session-continuity의 기존 권한·보존 규칙을 따른다.
