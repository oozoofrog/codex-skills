# Jev 스킬 모음 — codex-skills 통합판

이 폴더는 Jev 스킬 모음의 안내·출처를 담습니다. 최초 `jev-skills-collection-0.1.0` 통합 이후 현재 실행기는 `0.1.1`입니다. 스킬 7개는 저장소 루트에 각각 있으며 설치기는 기존 스킬·AGENTS.md·config.toml·모델·인증·훅을 변경하지 않습니다.

## 구성

| 스킬 | 용도 |
|---|---|
| `jev-workbench` | 공통 CLI와 12개 판단 절차 |
| `jev-decision` | 구현안·범위·다음 행동의 위임된 선택 |
| `jev-context` | 검색 후보의 관련성·알려진 값 선택 |
| `jev-triage` | 버그·제보 분류 |
| `jev-review-evidence` | 품질 신호·완료 주장과 증거 대조 |
| `jev-product-choice` | 명시한 제품·UX 기준의 대안 선택 |
| `jev-calibrate` | 판정 사례·질문 민감도 평가 |

## 설치

이 저장소가 이미 활성 스킬 루트이면 추가 복사는 필요 없습니다. 별도 작업 복제본이면 현재 사용하는 스킬 루트를 명시하세요. 아래 예시는 `~/.agents/skills`를 사용합니다. 기존 설치가 `~/.codex/skills`를 사용하는 환경에서는 `--dest`만 해당 위치로 바꿉니다. 설치기는 Codex 설정이나 스킬 검색 경로를 변경하지 않습니다.

```bash
# 저장소 루트에서 실행. 첫 명령은 미리보기만 합니다.
python3 scripts/install_jev_skills.py --dest "$HOME/.agents/skills" --preset all
python3 scripts/install_jev_skills.py --dest "$HOME/.agents/skills" --preset all --apply
```

동일 이름의 기존 스킬을 덮어쓰지 않습니다. 공통 스킬만 설치하려면 `--preset core`, 공식 TypeSafe 문서 스킬도 함께 복사하려면 `--with-typesafe`를 사용합니다. 외부 `jev-review`는 MCP 런타임이 포함되지 않아 참고용으로만 둡니다.

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
