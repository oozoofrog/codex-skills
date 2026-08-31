# GPT Pro standalone installation

## Default install

`gptpro`는 Desktop-only base이고 `gptpro-mcp`는 필수 read-only companion입니다. 기본 설치는 companion을 먼저 설치한 다음 base를 설치하고, owner-only descriptor에 exact entrypoint와 tree hash를 기록합니다.

```bash
python3 scripts/manage_skills.py list
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

기본 대상은 `${CODEX_HOME:-~/.codex}/skills`입니다. 격리 검증에는 `--dest /absolute/directory`를 사용합니다.

`gptpro-mcp`만 설치하는 명령은 migration/recovery 또는 maintainer 검증용입니다.

```bash
python3 scripts/manage_skills.py install gptpro-mcp --update
```

설치기는 symlink와 cache artifact를 거부·제외하고 staged tree hash를 확인한 뒤 원자 교체합니다. 내용이 다른 설치본은 `--update` 없이 덮어쓰지 않습니다.

## Local ChatGPT App binding

ChatGPT에서 생성한 private App ID는 mode `0600` 파일에 보관합니다. 저장소에 넣지 않습니다.

```bash
python3 scripts/manage_skills.py desktop-bind \
  --app-id-file /absolute/private/gptpro-app-id.txt \
  --dry-run

python3 scripts/manage_skills.py desktop-bind \
  --app-id-file /absolute/private/gptpro-app-id.txt \
  --confirm-bind
```

생성되는 companion은 apps-only local Plugin입니다. Skill, MCP server, shell tool, repository permission을 포함하지 않습니다. Raw App ID는 private `.app.json`에만 저장되고 receipt에는 hash만 남습니다. 이 binding은 모든 repository에서 재사용합니다.

## Legacy integrated installation

구형 통합 `gptpro`가 MCP lifecycle state를 소유하면 base update는 이를 종료된 것으로 추정하지 않습니다.

안전한 전환은 둘 중 하나를 요구합니다.

- terminal package receipt + exact-child stop
- terminal authorization + attended orphan clearance + `gptpro-mcp-residual-ownership-v1` receipt

두 번째는 `ownership_transferred=true`일 뿐 `exact_child_stop_proven=true`를 뜻하지 않습니다.

```bash
python3 scripts/manage_skills.py install gptpro-mcp --update

python3 scripts/manage_skills.py install gptpro --update --dry-run \
  --legacy-handoff-dir /absolute/path/to/handoff \
  --adopt-residual-mcp-state

python3 scripts/manage_skills.py install gptpro --update \
  --legacy-handoff-dir /absolute/path/to/handoff \
  --adopt-residual-mcp-state
```

Package가 실제로 손상·소실된 예외에서만 attended review 후 `--confirm-legacy-package-unavailable`을 사용합니다. Dry-run과 실제 install은 같은 transition evidence를 계산하지만 dry-run은 runtime, descriptor, 설치본을 변경하지 않습니다.

안정 오류 코드:

- `GPTPRO_MCP_RESIDUAL_ADOPTION_REQUIRED`
- `GPTPRO_LEGACY_PACKAGE_NOT_TERMINAL`
- `GPTPRO_MCP_RESIDUAL_RECEIPT_STALE`
- `GPTPRO_MCP_COMPONENT_REQUIRED`

## Post-install checks

```bash
python3 ~/.codex/skills/gptpro/scripts/gptpro.py desktop-doctor
python3 ~/.codex/skills/gptpro/scripts/gptpro.py capabilities
```

`desktop-doctor`는 전송하지 않습니다. macOS, ChatGPT app, Computer Use permissions, companion binding을 관찰합니다. Browser, CDP, remote debugging, Electron-private API는 사용하지 않습니다.

Plugin 설치는 [plugin-installation.md](plugin-installation.md)를 참고하세요.
