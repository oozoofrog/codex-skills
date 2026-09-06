# Astra Orchestrator Plugin

Astra 리더·워커·Git 전용 워커로 작업 조정을 요청할 때 사용하는 Codex 스킬입니다. 작은 작업은 현재 리더가 직접 완료하고, 독립 과제의 병렬화 이익이 있을 때만 위임합니다. 스킬 자체의 설명·편집이나 일반 단일 작업에는 자동 적용하지 않습니다.

## 설치

Marketplace에 이 버전이 반영된 뒤 필요한 Plugin만 설치합니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add astra-orchestrator@codex-skills
```

이미 등록한 marketplace는 `codex plugin marketplace upgrade codex-skills`로 최신 snapshot을 받은 뒤 설치합니다. 아직 원격에 반영하지 않은 checkout을 설치 대상으로 사용할 때는 첫 명령의 저장소 이름 대신 실제 checkout 절대 경로를 지정합니다. 기존 `codex-skills` 등록 경로를 변경하는 작업은 별도로 판단합니다.

새 Codex 작업에서 `astra-orchestrator:astra-orchestrator`가 노출되는지 확인합니다. 기존 사용자 로컬 `astra-orchestrator`와 Plugin을 함께 설치하면 같은 스킬이 중복 표시될 수 있으므로 사용할 배포 경로를 하나 선택합니다. 이 저장소에 Plugin을 추가하는 것만으로 사용자 로컬 스킬이 교체되지는 않습니다.

## 사용 조건과 호출

- 리더의 목표 설정은 `gpt-6-astra` / `xhigh`입니다. 스킬은 실행 중인 리더의 모델이나 추론 설정을 변경하지 않습니다.
- 내부 병렬 과제에는 서브에이전트를 사용하고, 사용자가 새 독립 작업 생성을 명시한 장기 과제에는 Codex 작업을 선택할 수 있습니다. 모델·effort·Standard 속도 지원과 관측 한계는 [세션 도구 안내](skills/astra-orchestrator/references/session-tools.md)를 따릅니다.
- 별도 MCP 서버, daemon, API key, 설치 hook은 없습니다. 모델이나 필요한 추론 수준을 사용할 수 없으면 해당 위임을 중단하고 이유를 보고합니다.

```text
$astra-orchestrator:astra-orchestrator
이 저장소의 요청된 기능을 완료해 주세요. 병렬화가 유리할 때만 위임하세요.
위임할 Git 변경은 별도 Git Steward가 맡고, 필요한 검증으로 완료 조건을 확인하세요.
```

| 역할 | 추론 수준 |
| --- | --- |
| Leader | `xhigh` |
| Worker | 기계적 작업 `medium`, 일반 구현 `high`, 전문 분석이 필요한 난제 `xhigh` |
| Git Steward | 조사 `medium`, 변경·일반 통합 `high`, 복잡한 충돌·이력 문제 `xhigh` |
| Independent Reviewer | 중요한 milestone·최종 독립 판정 `max` |

이는 사용자 지정 운영 정책이며 모델별 성능 비교 결과가 아닙니다. 스킬 설치나 역할 배정은 commit, push, 외부 전송 권한을 추가하지 않습니다.

## 구성과 유지보수

- [SKILL.md](skills/astra-orchestrator/SKILL.md): 실행 범위와 역할 정책
- [Skill README](skills/astra-orchestrator/README.md): 상세 예시와 로컬 제작 환경의 검증 기록
- [세션 도구 안내](skills/astra-orchestrator/references/session-tools.md): 현재 callable schema 확인과 설정 증거
- [Git Steward 규칙](skills/astra-orchestrator/references/git-steward.md): 작업 트리 소유권과 Git 통합
- [역할과 검토 판단](skills/astra-orchestrator/references/roles.md): 역할 선택과 독립 검토 기준
- [전달·반환 형식](skills/astra-orchestrator/references/packets.md): 작업 지시와 검증 결과

Plugin `0.1.0`은 2026-09-05 사용자 로컬 `astra-orchestrator`의 6개 파일을 내용 변경 없이 가져온 첫 저장소 배포본입니다. Skill 폴더의 기존 제작·실행 기록은 해당 환경의 과거 증거이며, 이 Plugin의 현재 설치나 실제 역할 실행을 증명하지 않습니다. 이 저장소에서는 `skills/astra-orchestrator/`를 수정하고 Plugin 버전·등록 정보·변경 기록을 함께 관리합니다. 사용자 로컬 설치본과 자동 동기화하지 않습니다.

Plugin `0.1.1`은 루트를 라우터·완료 조건으로 축소하고, 역할 판단을 `references/roles.md`로 분리했습니다. 고정 보고 서식과 횟수 기반 세션 교체를 제거하고 기존 권한 재사용, 필요한 검증만 수행, 서브에이전트와 별도 작업의 선택 기준을 명시합니다.
