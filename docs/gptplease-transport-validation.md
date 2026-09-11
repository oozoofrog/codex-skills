# gptplease 0.2.0 전송 런타임 검증

검증일: 2026-09-12 (Asia/Seoul). 대상: issue #45의 번들 상담 모듈. 의도한 실제 전송에는 합성 문장과 공개 테스트 fixture만 사용했다.

## 구현과 자동 검사

- `gptplease/runtime/consult.mjs`: 정책에서 확정한 설정을 실행하고, 단일 전송·전송 불명·응답 식별·취소·읽기 재개를 관리한다.
- `gptplease/runtime/cua-chatgpt.mjs`: 지원되는 CUA 브라우저 세션에서 Chat/Work 설정, 파일 선택기, 첨부 카드, 메시지 ID, 완료 응답 복사를 처리한다.
- transport는 Codex 모델 선택기·provider·route·config를 쓰지 않는다. 별도 서버와 ChatGPT→Codex 로컬 도구 연결도 만들지 않는다.
- 24개 Node 계약/adapter 검사와 10개 저장소 배포/문서 검사 통과. 독립 검증에서 발견한 비승인 첨부·복사된 코드 연산자 누락·복구 ID 재사용 문제는 회귀 검사에 포함했다.
- Skill 형식·Plugin manifest·standalone/Plugin 미러 일치 검사 통과.

## 실제 계정 E2E

| 실행 | 관측한 결과 |
| --- | --- |
| 새 Chat | GPT-5.6 Sol / `중간`, `CHAT-SMOKE-45` 전체 회수 |
| 기존 Chat 후속 요청 | 동일 URL에서 새 user/assistant 메시지 쌍 확인, `Chat transport confirmed.` 회수 |
| Chat Astra Pro | `MODEL_UNAVAILABLE`, 빈 새 입력창 유지, Send 미시도 |
| 새 Work 파일 상담 | GPT-5.6 Luna / `중간`, JSON·Markdown·Swift 세 파일의 실제 업로드와 전송 후 카드 일치, 원본 값 `7`·`ORBIT-45`·`11` 대조 |
| Work 후속 요청 취소/재개 | 전송 후 로컬 대기를 취소하고 동일 대화/메시지에서 읽기만 재개, 중복 Send 없음 |
| 장문 응답 | 80개 번호 줄과 종료 표식, 7,386자 Markdown 전체 회수 |
| 설치본 파일·코드 응답 | 고유 이름의 동일 내용 fixture 3개가 실제 수신됨. 원본 값 3개와 코드 블록의 들여쓰기·줄바꿈 및 종료 표식을 회수. 도구 모음 문구가 본문에 섞인 문제는 같은 응답의 읽기 복구로 수정 검증 |
| 생성 파일 | `transport-artifact.txt`의 실제 파일 ID·sandbox 링크 보존. 지원 UI 미리보기에서 `ARTIFACT-45` 확인. 자동 다운로드/byte 무결성 검증은 수행하지 않음 |

이는 실제 UI의 설정·완료·수신 증거다. 서버 내부 모델 ID나 모든 계정의 가용 모델을 검증했다는 뜻은 아니다.

## 설치와 노출

`codex plugin add gptplease@codex-skills --json`으로 0.2.0을 설치하고 installed/enabled를 확인했다. 코드 블록 회수 보완을 포함한 최종 캐시 버전은 `0.2.0+codex.20260911163819`다. 배포 원본과 설치 캐시 19개 파일이 모두 바이트 단위로 일치했다.

별도 stdio app-server에서 `skills/list(forceReload=true)`를 실행하여 새 캐시의 `gptplease:gptplease`가 활성 상태로 노출됨을 확인했다. 이 검사는 새 로더의 설치 스킬 노출 증거이며, 사용자 소유 Codex 작업을 새로 만들거나 그 작업에 상담을 맡긴 검사는 아니다.

설치본의 실제 전송·회수 전후 `config.toml`의 SHA-256이 같았다. 이 파일 검증과 transport에 모델/route 변경 동작이 없다는 소스 검사를 구분하며, 서버 내부 설정을 추정하지 않는다.

## 확인된 제한

- 한국어 Chat/Work UI와 작은 파일 3종을 실제 검증했다. 영어 계정, 대용량, 모든 파일 형식, 모든 Work 승인/입력 UI는 검증하지 않았다.
- 같은 이름의 파일을 다시 올리면 ChatGPT가 `(1)`을 붙일 수 있다. 정확한 파일명 계약이 달라지면 transport는 Send 전에 실패한다. 이 동작을 실제로 확인했다. 고유 이름의 승인된 복제본으로 다시 준비할 수 있지만 transport는 임의 이름 대응이나 본문 붙여넣기 대체를 수행하지 않는다.
- 자동 artifact 다운로드는 하지 않는다. 반환된 `bytes_retrieved:false`와 대화에 종속된 `sandbox:` 링크를 실제 로컬 파일이나 회수 완료 bytes로 해석하면 안 된다.
- 상태는 호출 세션과 명시적으로 보존한 checkpoint에 한정된다. 상태를 잃은 새 프로세스 전체에 대한 exactly-once 보장은 없다. 불명 Send의 재전송은 허용되지 않는다.

자세한 실행 순서는 [전송 계약](../gptplease/references/transport-contract.md)과 [복구 계약](../gptplease/references/transport-recovery.md)에 있다.
