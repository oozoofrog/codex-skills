# Astra Team Building

프로젝트 개발을 위한 팀 구성·위임·재편을 요청할 때 사용하는 Codex 스킬입니다. Astra·Sol·Luna와 thinking level을 작업의 난도·불확실성·검증 가능성에 맞춰 배정하고, 리더가 구현·검증·통합까지 조정합니다. 스킬 설명·편집이나 일반 단일 작업에는 자동 적용하지 않습니다.

기존 `astra-orchestrator`를 대체합니다. 별도의 `mixed-model` 선언이나 모든 모델 사용은 필요하지 않습니다. 고정된 인원수 대신 준비된 독립 과제, 가용 슬롯, 실제 격리 환경, 공유 자원, 통합 여력과 예산으로 팀 크기를 정합니다. 리더 단독도 정상적인 선택입니다.

```text
$astra-team-building으로 이 프로젝트의 목표를 완료해주세요.
필요한 역할과 모델·thinking level을 고르고 환경에 맞게 팀을 조절하세요.
```

특정 값을 지정할 수 있습니다. 예를 들어 “리더는 현재 설정을 유지하고 구현은 Sol/high, 독립 리뷰는 Astra/high로 하되 동시 worker는 하나까지만”이라고 요청하면 지정 범위에 우선 적용합니다. 모델명만 지정하면 effort는 과제에 맞춰 선택합니다.

## 운영 구조

[팀 설계](skills/astra-team-building/references/team-design.md)는 리더·탐색·구현·검증·리뷰·통합 역할을 제공하지만 역할별 세션 생성을 강제하지 않습니다. [모델 배정](skills/astra-team-building/references/model-routing.md)은 Astra low/medium, Sol medium, Luna high를 출발점으로 깊이를 조절합니다. 작업 결과로 확장·축소·재배정하고 사용자 지정값을 보존합니다.

[세션 도구](skills/astra-team-building/references/session-tools.md)의 실제 인자로 모델과 effort를 지정합니다. 현재 리더의 모델·전역 설정은 스킬 호출로 변경되지 않습니다. 서브에이전트는 파일시스템을 공유하므로 [작업 환경과 통합](skills/astra-team-building/references/workspaces-and-integration.md)의 한 worktree 한 writer와 공유 자원 조정이 필요합니다. 내부 과제는 서브에이전트, 사용자 소유의 별도 Codex 작업은 명시적 생성 요청이 있을 때 선택합니다.

[전달·상태](skills/astra-team-building/references/packets-and-state.md)는 필요한 입력·권한·완료 증거를 전달하고 긴 작업의 복구 지점을 하나로 유지합니다. [평가와 조정](skills/astra-team-building/references/evaluation.md)은 품질·전체 시간·사용량·재작업을 비교하며 검증되지 않은 비용 절감률을 약속하지 않습니다.

## 설치와 교체

이 저장소에서 `skills/astra-team-building/`이 원본이며 standalone 중복 사본은 관리하지 않습니다. Git marketplace에 변경이 게시된 뒤에는 다음과 같이 설치할 수 있습니다.

```bash
codex plugin add astra-team-building@codex-skills
codex plugin remove astra-orchestrator@codex-skills
```

아직 게시되지 않은 개발본은 로컬 personal marketplace에 이 Plugin을 등록하거나 skill 폴더 하나를 사용자 skill 위치에 설치할 수 있습니다. 같은 스킬을 여러 경로로 설치하지 않습니다. Git marketplace 등록을 로컬 경로로 몰래 바꾸지 않습니다. 구 설치 제거 전 설정·설치본을 백업하고 새 설치를 검증합니다. 과거 작업 기록과 사용자 데이터는 보존합니다.

새 Codex 작업에서 `$astra-team-building:astra-team-building`을 확인합니다(standalone은 `$astra-team-building`). 현재 진행 중인 대화의 이미 로드된 스킬은 설치 변경만으로 소급 교체되지 않습니다. Plugin 형식 검사, fresh loader 노출, 모델·effort의 실제 실행과 프로젝트 결과는 각각 별도로 검증합니다.
