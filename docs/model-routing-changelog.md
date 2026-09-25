# Model routing release notes — 2026-09-25

이 변경의 릴리스 기록입니다. [기존 변경 이력](../CHANGELOG.md)은 변경하지 않고 보존합니다. 원문 확인 범위와 설계는 [검토 문서](model-routing-review.md), 실행한 검사와 남은 검증은 [검증 문서](model-routing-validation.md)에 있습니다.

| Plugin | 이전 | 변경 |
| --- | --- | --- |
| gptplease | 0.2.0+codex.20260911163819 | 0.3.0 |
| astra-orchestrator | 0.1.1 | 0.2.0 |
| unreal-agent | 0.1.2 | 0.1.3 |
| session-continuity | 0.1.0 | 0.1.1 |

- Chat/Work의 실제 후보와 reasoning을 분리하고 명시 설정·Pro·Standard·단일 Send 경계를 보존했습니다. 상담 transport 코드는 변경하지 않았습니다.
- Astra-only 기본값에 명시적 mixed-model 선택을 추가했습니다. 위임 이익, 중요한 판단의 리더 유지, custom agent 덮어쓰기, 요청/관측 구분, 메인 컨텍스트와 한 worktree 한 writer를 보존합니다.
- Unreal runner의 Luna 자동 출발점을 high로 갱신하고 low의 명시 선택과 별도 평가를 구분했습니다. 외부 runner를 Codex 내부 위임 실패의 자동 우회로 사용하지 않습니다.
- 기존 task state가 있을 때 전체 작업 상태는 한 곳에서 관리하고 worker 배정만 참조하도록 연결했습니다. 일반 세션의 bootstrap·템플릿은 바꾸지 않았습니다.
- 표준 라이브러리 오프라인 평가 집계기, 합성 fixture, 단위/CLI 검사, 정적 배포 계약 검사와 17개 미실행 live 행동 시나리오를 추가했습니다. 이 도구는 에이전트를 실행하거나 가격·할당량·모델 품질을 검증하지 않습니다.
- standalone 수정 파일과 Plugin 미러를 동일하게 반영하고 기존 버전 기대값을 갱신했습니다. marketplace inventory, Jev 모델 라우팅 제외, 다른 Plugin·인증·설치 환경은 변경하지 않습니다.

X 원문 전문은 확보하지 못했습니다. 직접 확인하지 못한 원문 내용을 재작성한 전문이나 저자의 설치 지침으로 제시하지 않습니다. 이번 변경은 사용자 요구와 확인한 공식 자료를 기반으로 한 자체 구현입니다.
