# Jev 스킬 모음 — codex-skills 통합판

이 폴더는 Jev 스킬 모음의 안내·출처를 담습니다. 최초 `jev-skills-collection-0.1.0` 통합 이후 판단용 공통 실행기는 `0.1.1`입니다. 저장소 루트에는 판단 스킬 7개와 별도 실행 환경을 사용하는 데스크톱·브라우저 조작 스킬 2개가 있습니다. 판단 스킬 설치기는 기존 스킬·AGENTS.md·config.toml·모델·인증·훅을 변경하지 않습니다.

## 구성

| 스킬 | 용도 |
|---|---|
| `jev-workbench` | Jev 판단 작업을 시작하고 입력 준비·실행·결과 확인 |
| `jev-decision` | 구현 대안·작업 범위·다음 조사·사용할 스킬 중 선택 |
| `jev-context` | 읽을 자료의 우선순위를 정하고 원문에서 값·경로 선택 |
| `jev-triage` | 버그 제보를 기능 영역·사용자 영향·발생 조건으로 분류 |
| `jev-review-evidence` | 코드 검토 신호·완료 주장의 근거·추가 테스트 순서 평가 |
| `jev-product-choice` | 명시한 사용자 기준에 맞춰 제품 문구·UX 대안 중 선택 |
| `jev-calibrate` | 저장된 판정의 정확도와 한국어·표현·후보 순서 민감도 평가 |
| `jev-computer-use` | OCR·접근성 정보를 바탕으로 Jev와 Codex Luna가 macOS 화면 조작 |
| `jev-ultrafast` | Jev가 브라우저 행동을 선택하고 Codex Luna가 입력할 텍스트 생성 |

## 설치

이 저장소가 이미 활성 스킬 루트이면 추가 복사는 필요 없습니다. 별도 작업 복제본이면 현재 사용하는 스킬 루트를 명시하세요. 아래 예시는 `~/.agents/skills`를 사용합니다. 기존 설치가 `~/.codex/skills`를 사용하는 환경에서는 `--dest`만 해당 위치로 바꿉니다. 설치기는 Codex 설정이나 스킬 검색 경로를 변경하지 않습니다.

```bash
# 저장소 루트에서 실행. 첫 명령은 미리보기만 합니다.
python3 scripts/install_jev_skills.py --dest "$HOME/.agents/skills" --preset all
python3 scripts/install_jev_skills.py --dest "$HOME/.agents/skills" --preset all --apply
```

동일 이름의 기존 스킬을 덮어쓰지 않습니다. 공통 스킬만 설치하려면 `--preset core`, 공식 TypeSafe 문서 스킬도 함께 복사하려면 `--with-typesafe`를 사용합니다. 외부 `jev-review`는 MCP 런타임이 포함되지 않아 참고용으로만 둡니다.

### 데스크톱·브라우저 조작 스킬

`jev-computer-use/`와 `jev-ultrafast/`는 전역 설치의 스킬 본문·UI 메타데이터·실행 보조 파일을 내용과 실행 권한 그대로 보존한 사본입니다. 위 설치기의 `--preset all`은 기존 판단 스킬 7개를 대상으로 하며 이 두 어댑터를 설치하지 않습니다.

- [jev-computer-use](../../jev-computer-use/SKILL.md)는 `/Users/oozoofrog/.local/share/typesafe-computer-use`의 실행 환경을 사용합니다.
- [jev-ultrafast](../../jev-ultrafast/SKILL.md)는 `/Users/oozoofrog/.local/share/jev-ultrafast`의 실행 환경을 사용합니다.

현재 명령 예시와 런처는 원래 사용자 경로(`/Users/oozoofrog`) 및 전역 스킬 경로를 참조합니다. 다른 환경에 폴더만 복사해 독립 실행할 수 있는 패키지는 아닙니다. 실행 환경·의존성·인증·OS/브라우저 권한을 별도로 갖춰야 합니다. 비공개 `.env`, API 키, 로그인 정보와 화면 캡처·실행 기록은 가져오지 않았습니다.

가져올 때 원본 파일·권한 일치, 스킬 구조, 셸/Python 문법을 확인합니다. 실제 화면·브라우저 조작 검증을 의미하지 않습니다.

## 검증

```bash
python3 -m unittest discover -s tests/jev -v
python3 jev-workbench/scripts/jev_cli.py doctor
```

API 키 없이 실행되는 오프라인 검증입니다. 합성 응답의 통과는 실제 Jev 모델의 정확도나 API 호환성 검증이 아닙니다. 실제 API 호출에는 승인된 입력, TYPESAFE_API_KEY, 명시적인 `--live` 옵션이 필요합니다. 자세한 명령은 `../../jev-workbench/references/runtime.md`를 확인하세요.

0.1.1의 macOS·실제 API 확인 결과는 [TEST_REPORT.md](TEST_REPORT.md)에 있습니다. 질문 형식의 호환성, 모델 판단 품질, 새 세션의 실제 스킬 행동을 구분해 검토하려면 [평가 절차](../../jev-workbench/references/contract-calibration.md)를 참고하세요.

## 명시적 사용

```text
$jev-decision 구현 대안과 근거를 준비하고 위임한 최종 선택은 Jev에게 맡겨주세요.
$jev-review-evidence 완료 보고를 실제 테스트 본문·실행 결과와 대조해주세요.
$jev-calibrate 저장한 결정 사례의 후보 순서·표현 민감도를 평가해주세요.
```

판정은 `delegated`, `advisory`, `evaluation`으로 구분합니다. fixture 결과는 위임 실행용 결정이 아니고, Jev의 평가는 테스트 성공이나 실행 권한을 대신하지 않습니다. 전권 위임도 이 구현에서는 협력적 절차이며 우회 불가능한 실행 격리가 아닙니다.

## 출처와 라이선스

새 구현의 LICENSE는 각 스킬과 이 폴더에 보존했습니다. 외부 MIT 스킬 본문은 `vendor/*/SKILL.reference.md`로 보존하여 중복 스킬 발견을 막습니다. 파일명만 바뀌었고 원문 해시는 `sources/UPSTREAM.json`으로 검사합니다. 상류 커밋 고정과 원본 Git blob 동일성은 확인하지 않은 텍스트 스냅숏입니다.

## 통합 범위

기준 커밋 `08b16eb4704372625b94a66dd783c64adc63ae3b`의 저장소 구조·AGENTS.md·운영 지침을 확인하고 standalone 스킬로 통합했습니다. 기존 스킬, Plugin 미러, marketplace, AGENTS.md, .gitignore와 CI는 변경하지 않습니다. 새 Plugin 등록은 포함하지 않으므로 `codex plugin add jev-workbench@codex-skills` 설치를 안내하지 않습니다. 검증 범위는 [TEST_REPORT.md](TEST_REPORT.md), 이 모음의 변경 기록은 [CHANGELOG.md](CHANGELOG.md), 실제 반영 상태는 Git 이력을 확인하세요.
