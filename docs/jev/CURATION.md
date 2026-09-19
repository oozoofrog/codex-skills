# 외부 스킬 선별 결과

검토일: 2026-09-19. “좋은 스킬”은 인기도나 성능 우위의 객관적 순위가 아니라, 이번 목적에 대한 구조·범위·출처 적합성으로 골랐다.

## 포함: TypeSafe 공식 `typesafe-ai`

원문 위치: `vendor/typesafe-ai/SKILL.reference.md`, MIT 고지: `vendor/typesafe-ai/LICENSE`.
출처: https://github.com/typesafe-ai/skills

API 통합, 질문 설계, 분해·합성 패턴, 최신 문서로 돌아가는 흐름이 유용하다. 호출마다 전체 사이트를 읽지 않고 필요한 문서만 읽도록 안내한다. 별도 실행 서버를 요구하는 스킬은 아니다. `--with-typesafe`로 선택 설치할 수 있다. 이미 같은 이름이 설치되어 있으면 설치기는 덮어쓰지 않는다.

이 원문은 원래의 broad AI feature-building 용도다. 본 모음의 사용자 전송 승인과 결정 위임 규칙을 대신하지 않는다. 원문을 수정하여 우리 정책처럼 위장하지 않고 별도 snapshot으로 보존했다.

## 포함하되 자동 설치하지 않음: `jev-review`

원문 위치: `vendor/jev-review/SKILL.reference.md`, MIT 고지: `vendor/jev-review/LICENSE`.
출처: https://github.com/NiazMorshed2007/jev-review

평가→원인 조사→최소 변경→실제 검증의 흐름, 점수를 목표로 삼지 않는 중단 조건이 참고할 만하다. 그러나 이 원문은 `jev_review` MCP 도구를 요구하고, 최종 판단을 코딩 에이전트가 소유한다. 따라서 Jev의 delegated 최종 선택 계약과 같은 스킬로 취급하지 않는다.

원 플러그인의 MCP 서버·빌드 산출물·설정은 이 번들에 포함하지 않았고 실행하지 않았다. 원문은 참고 자료로 모았으며, 직접 사용하려면 upstream의 실제 도구 의존성까지 따로 검토해야 한다. 기존 키·설정·네트워크를 자동 연결하지 않는다. 설치기는 이 스킬을 설치 대상으로 제공하지 않는다.

본 번들의 `jev-review-evidence`는 CLI에 맞춘 새 advisory 스킬이다. 위 원문처럼 무조건 모든 비단순 작업에서 점수 루프를 강요하지 않고, 사용자가 요청한 검토와 의미 있는 변경 단위에만 적용한다.

## 링크·검토 메모만 포함: `building-with-jev-skill`

출처: https://github.com/dbreunig/building-with-jev-skill

입력 구성과 질문의 경계 사례를 진단하는 체크리스트가 참고할 만하다. 다만 확인한 공개 페이지에서는 재배포 허가를 확정하지 못했으므로 전체 본문을 복사하지 않았다. API 한도나 예제 임계값을 영구 규칙으로 가져오지 않는다. 공식 TypeSafe 스킬이 허용하는 bounded action selection까지 불필요하게 literal fact extraction으로 제한하지도 않는다.

## 원문 수집·고정 범위의 한계

이 환경에서는 Git clone/직접 파일 다운로드가 실패하여 웹 도구가 보여준 전체 텍스트를 스냅숏 파일로 옮겼다. 라이선스·출처는 함께 보존했다. 파일 내용의 재현을 위한 SHA-256을 기록했지만, upstream 원본 바이트와 동일함을 확인한 해시나 특정 커밋 pin은 아니다. `sources/UPSTREAM.json`의 upstream_commit은 null이며 main은 나중에 바뀔 수 있다. 배포 전 엄격한 공급망 검증이 필요하면 승인된 환경에서 실제 저장소를 커밋 단위로 다시 확인한다.

다른 저장소의 실행 스크립트는 실행하거나 자동 설치하지 않았다. 원문 안의 광범위한 지시는 이 모음의 안전·승인 경계를 넘어서는 상위 지침이 아니다.
