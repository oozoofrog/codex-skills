# Jev 실행기·스킬 검증

## 프로젝트 맥락·사용 대상 안내 — 2026-09-20

Jev 1.13의 공식 [모델](https://docs.typesafe.ai/models.md), [알려진 약점](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md), [확신도](https://docs.typesafe.ai/confidence.md), [복합 판단](https://docs.typesafe.ai/patterns/composite-scoring.md) 문서를 대조해 [프로젝트 적합성](../../jev-workbench/references/project-fit.md)을 추가했다. 넓은 구현·범위·제품 선택에서 필수 조건과 사용자 가치 우선순위를 먼저 확인하고, 불명확하면 위임 선택을 보류하도록 스킬 지침과 UI 설명을 좁혔다. API 요청 형식·실행기·모델·템플릿은 변경하지 않았다.

- `python3 -B -m unittest discover -s tests/jev -v`: **74개 통과**. 기존 실행기·설치기 계약 검사다.
- `python3 -B -m unittest discover -s scripts/tests -p test_document_links.py -v`: **2개 통과**. 새 참고 문서와 README 링크를 포함한다.
- 시스템 `skill-creator/scripts/quick_validate.py`로 변경한 `jev-workbench`, `jev-decision`, `jev-product-choice`: **3개 모두 통과**.
- 설치기를 임시 대상에 `all`로 실행해 판단 스킬 7개의 설치 파일을 소스와 바이트 비교: **모두 일치**, 새 `project-fit.md` 포함.
- `python3 -B jev-workbench/scripts/jev_cli.py doctor`: 실행기 `0.1.1`, 템플릿 12개, 네트워크 호출 없음. `git diff --check`: 통과.
- 전체 `python3 -B -m unittest discover -s scripts/tests -v`: **11개 중 10개 통과, 1개 실패**. `test_marketplace_points_to_available_plugins`의 예상 목록에 이미 저장소에 있는 `fast-jev-compaction` 항목이 빠져 있다. 해당 Plugin은 이 변경의 대상이 아니므로 marketplace·Plugin·테스트의 기존 불일치는 수정하지 않았다.

위 검사는 스킬 파일·링크·기존 실행기 계약을 확인한다. 새 지침에 따른 **새 Codex 세션의 실제 선택 행동**, 프로젝트별 Jev 판단 품질, UI 조작, 설치본의 새 세션 노출은 이 단계에서 검증하지 않았다. 이전 `evidence-check` 합성 사례 결과는 다른 절차의 정확도 근거가 아니다.

## 근거 검토 질문 개선 — 2026-09-19

0.1.1 실행기에서 `evidence-check` 질문·선택지 정의를 개선했습니다. 최종 변경 전후 비교는 한국어·영어 28개 원본 사례 × 3회 반복 × 두 문구로 총 336회이며, 변경 전 138/168에서 변경 후 168/168로 사전 정답 일치가 높아졌습니다. 마지막에 추가한 8개 사례는 45/48 → 48/48로 별도 집계했습니다. 실패한 첫 수정안까지 포함한 전체 576회, 평가 한계와 전달 문구는 [근거 검토 개선 검증](EVIDENCE_CHECK_VALIDATION.md)을 확인하세요.

## 0.1.1 리뷰 반영 — 2026-09-19

대상: `95adb7a14ba54094c4a1e52b3dbeb2e680322227` 기반 작업 트리의 Jev `0.1.1`. 환경: macOS, Python 3.14.7. 아래 결과는 소스·격리 설치·실제 API 범위를 구분한 기록이며 배포 또는 개인 설치 갱신 완료를 뜻하지 않는다.

### 로컬 검사

- 수정 전 기본 환경: 기존 64개 검사에서 실패 1건·오류 32건. macOS `/var` 시스템 별칭 거부와 참고 문서 전사 오타가 원인이었다.
- 새 회귀 검사 10개를 먼저 실행하여 실패 6건·오류 3건, 기존 보호 동작 1건 통과를 확인했다. 전송 순서·승인 해시, 모델 별칭, null 설명, 시스템/사용자 링크 구분, 이전 기록 보존을 대상으로 한다.
- 수정 후 `python3 -B -m unittest discover -s tests/jev -v`: **74개 모두 통과**. `TMPDIR` 우회 없이 macOS 기본 환경에서 실행했다.
- `python3 -B -m unittest discover -s scripts/tests -v`: **11개 모두 통과**. 기존 marketplace·Plugin 미러·문서 링크 관련 검사 포함.
- `python3 -m py_compile jev-workbench/scripts/jev_cli.py scripts/install_jev_skills.py tests/jev/test_review_regressions.py`: 통과.
- 시스템 `quick_validate.py`로 스킬 7개를 각각 검사: 모두 통과. 이름·frontmatter·미완성 표시 검사이며 에이전트 행동 평가가 아니다.
- Jev Markdown 36개 문서의 링크 대상 검사: 깨진 로컬 Markdown 링크 없음.
- `python3 -B jev-workbench/scripts/jev_cli.py doctor`: 버전 `0.1.1`, 템플릿 12개, `network_called: false` 확인. doctor는 키 존재만 확인하고 키 값은 출력하지 않는다.
- 설치기를 임시 폴더에 `--preset all --apply`로 실행: 7개 설치 성공. 설치본에서 12개 workflow의 `prepare → run --fixture → check`, 총 36개 명령 모두 성공.
- 이전 리뷰에서 실제 생성한 0.1.0 실행 폴더를 새 CLI의 `status`로 읽고 모든 파일 해시가 그대로임을 확인했다. 별도 회귀 검사에서 이전 live receipt의 조회·캐시 반환 및 새 전송·위임 후속 진행 거부를 확인했다.
- jev-review 참고 본문의 `introducedced`를 공개 원문의 `introduced`로 복원한 뒤 기존 `local_skill_sha256`과 일치했다. 출처 해시를 현재 파일에 맞춰 덮어쓰지 않았다.

### 실제 TypeSafe API 왕복

새로 작성한 비민감 합성 평가 입력을 `authority=evaluation`, `is_example=false`로 준비했다. 번들 예제의 플래그만 바꾸거나 저장소 코드·사용자 자료를 전송하지 않았다. `prepare`의 전송 해시로 `run --live --approved-sha ...`를 각각 한 번 실행하고 일반 `check`로 확인했다. 자동 재시도는 없었다.

동일 입력의 보고 문장은 “The app crashes every time it opens. No workaround is available.”였다. 세 질문은 명시된 발생 조건(Choice, launch/reconnect의 설명은 null), 재연결 언급 여부(Noul), 보고된 기능 영향(Score, 0–2)이었다.

| 요청 모델 | 반환 모델 | Choice | Noul | Score | 입력/출력 토큰 | CLI 왕복 시간 |
|---|---|---|---|---|---|---|
| jev-1.13.0 | jev-1.13.0 | launch | 0.01 | 2.0 | 445 / 75 | 0.725초 |
| jev-latest | jev-1.13.0 | launch | 0.01 | 2.0 | 445 / 75 | 0.596초 |
| jev-preview | jev-1.13.0 | launch | 0.01 | 2.0 | 445 / 75 | 0.662초 |

세 요청 모두 정상 receipt와 `check` 성공을 확인했다. 전송 해시는 순서대로 `f960c63c7e84699d18ef887bfad4199942e0f2b083e10c4a05263aa0591d760b`, `bf46954bd864965666f0b9542709b6b3938cd260d8b8902ada750da402bcdcb0`, `46174456ec8bb42c429c42c52d3faf59cc9768466f0afd6cdea4779398f17525`다. 위 시간은 각 1회 CLI 실행의 관측값이며 성능 벤치마크가 아니다.

이 검사는 3가지 질문 형식, 공식 모델 별칭, Choice null 설명의 실서비스 호환성 증거다. 같은 단일 영어 사례의 반복이므로 한국어·실제 개발 판단 정확도나 후보 순서 민감도의 모델 품질 평가로 일반화하지 않는다. 전송 순서가 유지되고 승인 해시가 바뀌는지는 로컬 전송 경계 회귀 검사로 확인했다.

### 확인하지 않은 범위

- 12개 workflow 전체의 실제 모델 판단 정확도, 한국어/영어 비교, 독립된 검증용 사례에서의 성능.
- 새 Codex 세션의 스킬 발견·명시적 호출·지침 준수. 기존 명시적 호출 정책은 유지했으며 일반 목록에서의 자동 노출을 요구하지 않는다.
- 개인 스킬 루트의 기존 설치 갱신, Plugin 배포, 원격 CI, 커밋·푸시.

스킬·실행기·모델·에이전트 행동을 나누는 후속 평가 절차는 [계약 보정 지침](../../jev-workbench/references/contract-calibration.md)에 있다. 현재 변경의 명령 로그, 준비 입력, API 원 응답과 receipt는 작업의 검증 산출물로 별도 보존했다. API 키는 파일이나 로그에 기록하지 않았다.

---

## 0.1.0 최초 통합 당시의 기록

아래 내용은 최초 통합 때의 환경과 결과를 보존한 것이다. 현재 macOS 검증 결과는 위 0.1.1 항목을 따른다.

검증일: 2026-09-19
기준 커밋: `08b16eb4704372625b94a66dd783c64adc63ae3b`

## 실제 수행한 검사

- `python3 -m unittest discover -s tests/jev -v`: **64개 테스트 통과**. 준비된 저장소 통합 ZIP을 작업 디렉터리에 풀고 Python 3.13.5에서 실행했다. 합성 provider 응답과 임시 디렉터리를 사용하는 오프라인 검사다.
- `python3 -m py_compile jev-workbench/scripts/jev_cli.py scripts/install_jev_skills.py`: 통과.
- `python3 jev-workbench/scripts/jev_cli.py doctor`: 버전 `0.1.0`, 템플릿 12개, `network_called: false`, `typesafe_key_present: false`, `authority_enforcement: cooperative` 확인.
- `git diff --cached --check`: 통합 ZIP의 추가 파일을 임시 Git 인덱스에 넣어 검사했고 공백 오류가 없었다.
- 원격에 준비된 스킬 7개와 `tests/`의 Git tree SHA가 검증한 통합 ZIP에서 파일 내용과 실행 모드를 사용해 계산한 tree SHA와 일치함을 확인했다. 설치기 blob SHA도 일치했다.
- 원격 기준 tree와 준비된 tree를 비교했다. 기존 최상위 파일·스킬·Plugin·marketplace는 동일했고, `docs/`와 `scripts/`는 기존 항목을 보존하면서 Jev 항목만 추가했다.
- 원격 준비 문서의 README·CURATION·INTEGRATION·CHANGELOG를 읽고, README가 참조하는 누락된 이 검증 보고서를 추가했다.

## 범위와 한계

이 검사는 CLI 계약·예제·패키징 동작 검사이며 Jev 모델의 판단 정확도나 실서비스 API 호환성 검증이 아니다. 실제 TypeSafe API 호출, Classifier 연동, macOS 설치, 사용자의 Codex 새 세션에서 스킬 노출, 원격 CI는 수행하지 않았다. 컨테이너의 공개 Git clone은 DNS 오류로 실패하여 저장소 읽기·반영은 연결된 GitHub 도구로 수행했다. 저장소 전체를 로컬에 복제하지 않았으므로 기존 `scripts/tests` 전체 회귀 실행으로 보고하지 않는다.

이번 배포는 standalone 스킬이다. Plugin marketplace 등록이나 기존 Codex 모델·인증·설정 변경을 포함하지 않는다. 스킬 설치는 저장소 반영과 별개이며, 설치 절차는 [README.md](README.md)에 있다. 커밋·푸시 완료 여부는 이 문서의 문구가 아니라 실제 GitHub `main` 참조와 커밋 이력으로 확인한다.
