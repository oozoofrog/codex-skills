# codex-skills

로그인된 ChatGPT Pro와 Codex가 안전하게 협업하도록 돕는 `gptpro` 전용 저장소입니다. 일반 로컬 작업이나 OpenAI API 호출에는 사용하지 않으며, 사용자가 ChatGPT Pro 협업을 명시적으로 요청한 경우에만 plan, ask, review, debug, architecture 상담을 준비합니다.

## 제공 패키지

| Package | 용도 |
|---|---|
| `gptpro` | 승인된 browser handoff와 명시적으로 선택한 실험적 read-only Web MCP를 통해 로그인된 ChatGPT Pro general Chat에 자문을 요청하고, 결과를 Codex가 독립 검증합니다. |

저장소에는 같은 내용을 두 형태로 제공합니다.

- `gptpro/`: `$skill-installer` 또는 로컬 checkout으로 설치하는 standalone Skill
- `plugins/gptpro/`: Codex Plugin marketplace용 skills-only Plugin

두 Skill 복사본은 검증 시 byte-for-byte 일치를 요구합니다.

## 설치

Codex에 다음과 같이 요청할 수 있습니다.

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

Plugin marketplace 설치는 [Plugin 설치 안내](docs/plugin-installation.md), checkout에서의 안전한 설치·update는 [standalone 설치 안내](docs/selective-installation.md)를 참고하세요. 설치 후 첫 상담과 승인 흐름은 [한국어 사용자 매뉴얼](gptpro/references/user-manual.md)에 정리되어 있습니다.

## 사용 예시

일반 상담은 검증된 GitHub commit을 우선하고, 사용자가 정확한 전송 대상과 바이트를 승인한 뒤 진행합니다.

```text
$gptpro review 모드로 현재 변경을 검토할 상담 패키지를 준비해주세요.
```

실험적 Web MCP는 자동 선택되지 않습니다. 저장소 읽기 또는 분석 협업이 필요할 때만 `mcp-read`나 `mcp-research`를 명시적으로 요청하며, 별도의 공개 범위·예산·만료·전송 승인이 필요합니다.

```text
$gptpro mcp-research로 이 저장소의 변경과 테스트 누락을 분석할 상담을 준비해주세요.
```

ChatGPT Pro의 답변은 자문일 뿐입니다. Codex가 현재 저장소에서 다시 확인하고 관련 테스트를 실행한 뒤에만 적용합니다.

## Maintainer workflow

```bash
python3 scripts/manage_skills.py list
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

기본 설치 위치는 `${CODEX_HOME:-~/.codex}/skills/gptpro`입니다. 다른 위치에서 검증하려면 `--dest`를 사용합니다.

핵심 검증 명령:

```bash
python3 gptpro/scripts/validate_structure.py
python3 -m unittest discover -s gptpro/tests -v
python3 -m unittest discover -s scripts/tests -v
```

변경 기록은 [CHANGELOG.md](CHANGELOG.md)를 참고하세요.
