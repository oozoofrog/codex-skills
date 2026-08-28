# codex-skills

로그인된 ChatGPT Pro와 Codex가 안전하게 협업하도록 돕는 `gptpro` 전용 저장소입니다. 일반 로컬 작업이나 OpenAI API 호출에는 사용하지 않으며, 사용자가 ChatGPT Pro 협업을 명시적으로 요청한 경우에만 plan, ask, review, debug, architecture 상담을 준비합니다.

## 제공 패키지

| Package | 용도 |
|---|---|
| `gptpro` | 명시적으로 요청한 프로젝트 상담이 실제 문맥 탐색을 필요로 하면 승인 대기 `mcp-research`를 기본 제안하고, 새 ChatGPT Pro general Chat에서 자문을 받은 뒤 Codex가 독립 검증합니다. |

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

작은 고정 문맥의 일반 상담이나 사용자가 GitHub/text 경로를 지정한 경우에는 검증된 GitHub commit을 우선하고, 사용자가 정확한 전송 대상과 바이트를 승인한 뒤 진행합니다.

```text
$gptpro review 모드로 현재 변경을 검토하되 공개 범위는 src와 tests로 제한해 상담 패키지를 준비해주세요.
```

명시적인 `$gptpro` 프로젝트/저장소 상담이 Pro의 실제 문맥 검색·읽기·탐색을 필요로 하면 Skill은 최소 범위의 `mcp-research` package를 기본 제안합니다. 이 라우팅은 공개나 전송 승인이 아니며, CLI의 `auto`가 MCP를 선택한다는 뜻도 아닙니다. 별도의 공개 범위·도구·예산·만료·ledger·전송 승인을 받은 뒤에만 활성화하고, `mcp-read`는 사용자가 기존 3-tool reader를 명시한 경우에만 사용합니다.

반복적인 Schema-4 상담은 사용자가 별도로 생성한 범위 제한형 상시 승인 profile을 사용할 수 있습니다. 같은 repository·path·mode·model·app/workspace·Tunnel profile·dirty 정책·예산 안의 package만 exact receipt로 자동 승인하며, 범위 확대·외부 evidence/supplement·브라우저 신뢰 경계·Codex note별 승인은 계속 사람 확인을 요구합니다.

```text
$gptpro mcp-research로 src와 tests의 변경과 테스트 누락을 분석할 상담을 준비해주세요.
```

각 package는 이전 대화, Work, Project, custom GPT가 아닌 **비어 있는 새 general Chat**에서 한 번만 전송합니다. 제출 기록에는 canonical `chatgpt.com/c/<id>` URL과 새 Chat 확인이 필수이며, 다른 로컬 handoff에 이미 묶인 URL은 거부됩니다.

저장소 밖의 요구사항처럼 검토된 UTF-8 문서가 필요하면 파일을 브라우저에 업로드하지 않고 보충 snapshot으로 요청할 수 있습니다. repository 범위도 함께 지정해야 하며, 원본 locator는 package에 저장되지 않지만 shell/process/tool log에는 보일 수 있습니다.

```text
$gptpro review 모드로 src와 tests를 검토하면서 /절대/경로/requirements.md를 requirements 보충 문서로 읽어주세요. 브라우저에는 원본 파일을 업로드하지 마세요.
```

작은 문서가 아니라 prompt·선택 repository 문맥·보충 문서를 합친 complete payload가 paste 한도 안이어야 합니다. 큰 one-line artifact를 포함한 Schema 4 제약과 안전한 로컬 파일 계약은 [Supplemental text documents](gptpro/references/supplemental-documents.md)를 참고하세요.

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
