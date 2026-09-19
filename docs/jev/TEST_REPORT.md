# Jev 0.1.0 저장소 반영 검증

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
