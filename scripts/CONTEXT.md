# CONTEXT.md

## Scope
- `scripts/`는 저장소 자체를 동기화하거나 자동화하는 운영 스크립트를 둔다.
- 상위 규칙은 [../AGENTS.md](../AGENTS.md)를 따른다.

## Key Files
- [sync_repo.sh](./sync_repo.sh): fetch/rebase/add/commit/push 흐름을 묶는 핵심 동기화 스크립트
- [sync_skill_mirrors.py](./sync_skill_mirrors.py): standalone Skill과 Plugin 사본의 내용·모드 일치 검사 및 원자 동기화
- [auto_sync_daemon.py](./auto_sync_daemon.py): 변경 감시와 debounce 기반 자동 동기화 실행기
- [install_auto_sync_launchd.sh](./install_auto_sync_launchd.sh): launchd 설치 진입점
- [uninstall_auto_sync_launchd.sh](./uninstall_auto_sync_launchd.sh): launchd 제거 진입점
- [install_jev_skills.py](./install_jev_skills.py): 명시한 Jev standalone 스킬만 기존 경로를 덮어쓰지 않고 설치

## Local Rules
- shell script는 `bash -n`, Python script는 `python3 -m py_compile`로 먼저 검증하기.
- 배포·동기화 변경은 `python3 -m unittest discover -s scripts/tests -v`로 검증하고 무관한 패키지 변경을 보존하기.
- 안전한 경우를 제외하면 실 repo 상태를 바꾸는 명령보다 dry-run 또는 임시 디렉토리 재현을 우선하기.
- launchd 래퍼는 `sync_repo.sh`와 `auto_sync_daemon.py`의 경로 계약을 깨지 않게 유지하기.
- Jev 설치 변경은 `python3 -m unittest discover -s tests/jev -v`도 실행한다. macOS 기본 임시 경로와 사용자 생성 symlink 거부를 함께 검증하며, 임시 경로 우회만으로 플랫폼 통과를 보고하지 않는다.

## Verification Notes
- `sync_repo.sh`를 수정하면 `--dry-run` 시나리오를 먼저 확인하기.
- daemon이나 launchd 스크립트를 수정하면 경로, 기본값, 로그 경로를 함께 점검하기.
