# Astra Team Building 0.1.0 검증 기록

확인일: 2026-09-26. `astra-orchestrator`를 [Astra Team Building](../plugins/astra-team-building/README.md)으로 교체한 로컬 작업의 기록이다. 원격 배포, 모든 모델/effort의 실제 실행, 최적 비용 측정을 뜻하지 않는다.

## 변경과 확인

- 기존 Plugin 원본 11개 파일을 제거하고 새 skills-only Plugin 10개 파일을 만들었다. 새 SKILL.md는 32줄이며 팀 설계·모델 배정·세션 도구·환경/통합·전달/상태·평가를 references로 분리했다.
- marketplace의 기존 위치에서 이름과 source 경로를 교체했다. 다른 항목의 순서·정책은 유지했다. 설치 안내·현재 사용 예·배포 검사·행동 시나리오를 갱신했다. 과거 검증·변경 이력은 과거 기록임을 표시해 보존했다.
- 모델별 시작 effort는 확인한 공식 문서, callable 필드와 지원 수준은 현재 제작 호스트 schema를 근거로 구별했다. 역할별 배정표와 팀 크기 조정은 운영 정책이며 최적성 실측 결과가 아니다.

## 실행한 정적 검사

```bash
python3 -m py_compile scripts/tests/test_plugin_distribution.py scripts/tests/test_model_policy_contracts.py
python3 -m unittest discover -s scripts/tests -v
python3 /Users/oozoofrog/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/astra-team-building/skills/astra-team-building
python3 /Users/oozoofrog/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/astra-team-building
git diff --check
```

Python compile과 전체 저장소 검사에는 저장소 밖의 `PYTHONPYCACHEPREFIX`를 지정했다. 전체 **63개 검사 통과**. Skill/Plugin 형식, marketplace inventory, UI 메타데이터 일치, 로컬 문서 링크, 모델 정책 시나리오의 구조를 확인했다. 24개 시나리오의 구조 검사가 24개 실제 실행을 뜻하지는 않는다.

## 독립 forward test

별도 평가 세션에 스킬과 격리 fixture 및 원 요청만 제공했다. 저장소 검사나 기대 답은 전달하지 않았다.

- 실제 과제: `format_percent(None)`은 대시를 유지하고 `format_percent(0)`은 `0%`를 표시하며 기존 소수·음수 형식을 보존한다.
- 실제 행동: 평가 세션은 추가 worker 없이 작은 변경을 직접 완료했다. 추가한 0 회귀 검사가 수정 전 실패했고, 조건 수정 후 기존 3개와 합쳐 **4개 통과**했다. 실제 파일과 RED/GREEN 로그를 회수해 확인했다.
- 계획만의 과제 6개: 고위험 read-only 계약, 명시 모델 미지원, 단일 실기기 공유, 통합 적체, 모델만 명시한 배정, 슬롯이 없는 idle worker 재사용. 각 역할·설정·소유권·보류 조건을 보고했다. 계획 응답은 실제 spawn·통합·기기 검증으로 계산하지 않는다.
- 평가 세션의 실제 모델/effort 관측 필드는 없으므로 unverified다. 이 검증을 Astra/Sol/Luna의 성능 비교로 사용하지 않는다.

평가에서 실행한 명령:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_percent.py
```

## 로컬 설치와 fresh loader

설치 전 config, Plugin inventory, marketplace inventory, 기존 원본과 설치본을 백업했다. Git 기반 `codex-skills` 등록은 유지하고 새 Plugin을 로컬 personal marketplace에 설치했다.

```bash
codex plugin add astra-team-building@personal --json
codex plugin list --json
codex plugin marketplace list --json
```

구 Plugin은 앱의 `uninstall_plugin` 도구로 정확한 ID `astra-orchestrator@codex-skills`를 지정해 제거했다. 설치본과 cache 부재를 확인했다. 새 `astra-team-building@personal` 0.1.0은 installed/enabled이며 repository·personal source·cache의 10개 파일 내용과 모드가 일치했다.

새 `codex app-server --stdio` 프로세스에서 `initialize` 후 `skills/list`에 repository cwd와 `forceReload: true`를 전달했다. 새 스킬 `astra-team-building:astra-team-building` 한 개가 user/enabled로 발견됐고 구 스킬은 없었으며 loader error는 없었다. 이는 별도 프로세스의 로더 관측이며 현재 진행 중인 앱 대화의 스킬 소급 교체를 뜻하지 않는다.

설정의 의미상 차이는 구 Plugin 제거와 새 Plugin 활성화 두 키뿐이었다. marketplace 등록과 기존 personal 항목은 유지됐다. 다만 작업 중 `gptplease`, `session-continuity`, `unreal-agent`의 설치 버전도 변경된 것으로 관측됐다. 해당 cache 생성 시각(10:29)은 이번 새 Plugin cache 생성(10:37)보다 앞선다. 이 상태를 되돌리지 않았고 전체 inventory가 동일하다고 주장하지 않는다. 버전 외 다른 Plugin inventory 필드는 동일했다.

원본 로그·fixture·백업·설치 대조 결과는 제작 환경의 `/Users/oozoofrog/.codex/backups/astra-team-building-20260926-102703/`에 보존했다. 이 디렉터리는 배포 Plugin에 포함하지 않는다.

## 남은 확인

- 실제 Astra·Sol·Luna 혼합 팀의 spawn/반환·effort 전환·worktree 통합·공유 자원 동작은 이 작업에서 E2E 검증하지 않았다.
- 시간·사용량·비용 절감률과 최적 인원은 측정하지 않았다. 실제 프로젝트에 적용한 결과로 배정을 조정한다.
- 현재 앱 작업에는 이미 읽은 구 스킬이 남을 수 있다. 새 작업에서 새 스킬을 호출한다.
- 커밋·push·Git marketplace 원격 게시는 수행하지 않았다. 로컬 사용은 personal 설치본, 저장소 원본은 새 Plugin 경로다.
