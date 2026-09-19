# 호환성과 확인 범위

- 대상: 로컬 파일·프로세스를 사용할 수 있는 Codex 환경. 0.1.1은 macOS에서 CLI와 격리 설치를 검증한다. 개인 설치 갱신 및 새 Codex 세션의 실제 호출 여부는 별도다.
- 스킬 형식: SKILL.md의 name/description, 선택적 agents/openai.yaml. 이름이 다른 7개 새 스킬이다.
- Python: 3.10+ 표준 라이브러리. 실제 검증 환경은 macOS/Python 3.14.7이며 다른 Python 버전 전체를 시험한 것은 아니다. 상세 결과는 [TEST_REPORT.md](TEST_REPORT.md)에 기록한다.
- macOS의 `/tmp`·`/var`가 각각 `/private/tmp`·`/private/var`로 해석될 때만 시스템 별칭으로 허용한다. 하위 사용자 생성 symlink는 계속 거부한다.
- API: `jev-1.13.0`·`jev-latest`·`jev-preview`의 Choice·Score·Noul 왕복과 Choice `null` 설명을 실제 서비스에서 확인했다. 모델별 판단 정확도 검증과는 구분한다.
- 기록: 0.1.0 실행 폴더는 원래 해시 계약으로 읽기만 지원한다. 0.1.1의 전송 순서·승인 해시를 이전 기록에 덮어쓰거나 자동 재전송하지 않는다.
- 기본은 명시적 호출: 새 스킬의 allow_implicit_invocation=false. 원하지 않는 외부 호출과 중복 스킬 활성화를 줄인다. API 전송 승인은 별도다.
- 개인 설치 경로는 현재 공식 문서의 ~/.agents/skills. 기존 CODEX_HOME, ~/.codex/config.toml, ChatGPT 앱 내장 CLI, API 키·모델·provider는 변경하지 않는다.
- 설치기는 --dest로 임의의 실제 스킬 루트를 지정할 수 있다. 선택한 Codex 버전이 그 루트를 읽는지는 사용자가 확인한다. ~/.codex/skills를 유일한 경로라고 가정하지 않는다.
- 이 ZIP을 일반 ChatGPT 대화에 첨부하는 것만으로 사용자 Mac의 CLI가 실행되는 것은 아니다. 단일 스킬 ZIP은 SKILL 업로드를 지원하는 환경의 명시적 설치용이며, 코드 실행·네트워크·키 가용성을 별도로 확인해야 한다.
- 외부 스킬 원문은 라이선스에 따라 분리 보관했다. jev-review 원문은 MCP 의존성이 없어졌다고 주장하지 않는다.

출처: https://developers.openai.com/codex/skills/ (확인 2026-09-19)
