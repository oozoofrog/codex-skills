# CONTEXT.md

## Scope
- `.system/`은 upstream 시스템 스킬의 미러를 보관한다.
- 일반적인 저장소 작업보다 upstream 동기화 또는 의도적 패치 작업에서 더 자주 읽는다.
- 전역 규칙은 [../CLAUDE.md](../CLAUDE.md)를 따른다.

## Key Files
- [.codex-system-skills.marker](./.codex-system-skills.marker): 시스템 스킬 미러 마커
- [skill-creator/SKILL.md](./skill-creator/SKILL.md): 새 스킬 생성·업데이트 워크플로
- [skill-installer/SKILL.md](./skill-installer/SKILL.md): curated/github 스킬 설치 워크플로

## Local Rules
- upstream 미러는 불필요하게 재구성하지 말기.
- 여기의 스크립트를 수정하면 해당 시스템 스킬의 기대 동작과 충돌하지 않는지 확인하기.
- 저장소 전용 규칙은 가능하면 루트 문서나 로컬 skill 디렉토리에 두고, `.system/`에는 upstream 성격을 유지하기.

## Verification Notes
- `.system/skill-creator`를 건드리면 `quick_validate.py`와 생성 스크립트 경로를 함께 점검하기.
- `.system/skill-installer`를 건드리면 Python 스크립트 문법과 진입점 파일명을 함께 확인하기.
