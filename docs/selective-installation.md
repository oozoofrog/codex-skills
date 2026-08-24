# gptpro standalone installation

`scripts/manage_skills.py`는 이 checkout의 `gptpro` standalone Skill만 조회하고 설치합니다. 다른 패키지는 발견하거나 복사하지 않습니다.

## 설치 상태 확인

```bash
python3 scripts/manage_skills.py list
python3 scripts/manage_skills.py list --format json
```

상태는 다음 중 하나입니다.

- `not-installed`: 대상 위치에 `gptpro`가 없음
- `current`: 설치본이 현재 checkout과 byte-for-byte 일치
- `different`: 유효한 설치본이 있지만 내용이 다름
- `conflict`: 대상 경로가 유효한 Skill 디렉터리가 아님

## 설치·미리보기·update

```bash
python3 scripts/manage_skills.py install gptpro
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

기본 대상은 `${CODEX_HOME:-~/.codex}/skills`입니다. 격리된 검증에는 `--dest <directory>`를 사용하세요.

내용이 다른 기존 설치본은 `--update` 없이 교체하지 않습니다. update는 staging 복사본의 tree hash를 확인한 뒤 원자적으로 교체하며, 교체 실패 시 이전 설치본을 복원합니다. Skill 내부 symlink는 거부하고 `__pycache__`, `*.pyc`, `*.pyo` 같은 cache artifact는 제외합니다.

## GitHub에서 바로 설치

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

bundled installer는 기존 대상 경로를 덮어쓰지 않습니다. 기존 설치를 갱신하려면 검토한 checkout에서 위의 `--update` 흐름을 사용하세요.

Plugin 설치는 [plugin-installation.md](./plugin-installation.md)를 참고하세요.
