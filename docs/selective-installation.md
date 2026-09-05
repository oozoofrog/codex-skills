# gptpro standalone installation

`gptpro` 하나만 설치합니다.

```bash
python3 scripts/manage_skills.py list
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

기본 대상은 `${CODEX_HOME:-~/.codex}/skills/gptpro`입니다. `--dest /absolute/directory`로 격리 검증할 수 있습니다. 다른 설치본은 `--update` 없이 덮어쓰지 않으며 staged tree hash 확인 후 원자 교체합니다. `* 2.*`, cache, `.DS_Store`, symlink는 설치하지 않습니다.

## Legacy MCP transition

구형 `gptpro-mcp`가 설치되어 있으면 dry-run과 실제 install이 같은 observation-only 진단을 수행합니다. 다음이 모두 필요합니다.

- `--legacy-handoff-dir /absolute/path/to/exact-package`로 정확한 과거 package 지정
- package evidence `verified`, binding `same_package`
- authorization `revoked|expired`
- controller lease `not_live|absent`
- `exact_child_stop_proven=true`

package 경로가 없으면 `GPTPRO_LEGACY_PACKAGE_EVIDENCE_REQUIRED`, 나머지 조건이 하나라도 없으면 `GPTPRO_LEGACY_MCP_ACTIVE`로 중단합니다. 먼저 다음처럼 같은 package로 dry-run과 실제 update를 각각 실행합니다.

```bash
python3 scripts/manage_skills.py install gptpro --update --dry-run \
  --legacy-handoff-dir '/absolute/path/to/exact-terminal-package'
python3 scripts/manage_skills.py install gptpro --update \
  --legacy-handoff-dir '/absolute/path/to/exact-terminal-package'
```

안전한 실제 update는 기존 companion과 `.gptpro-components.json`을 macOS Trash로 옮깁니다. Historical handoff/receipt state는 보존합니다.

## Post-install

```bash
python3 ~/.codex/skills/gptpro/scripts/gptpro.py capabilities --json
python3 ~/.codex/skills/gptpro/scripts/gptpro.py init --json
python3 ~/.codex/skills/gptpro/scripts/gptpro.py desktop-doctor --json
```

`desktop-launch`는 owner-only 전용 프로필과 loopback 포트 9223으로 두 번째 ChatGPT 프로세스를 실행합니다. 평소의 ChatGPT 앱은 계속 열어둘 수 있습니다. Installer나 Skill은 어느 ChatGPT/Codex 프로세스도 자동 종료·재시작하지 않습니다.
