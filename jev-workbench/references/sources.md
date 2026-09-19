# 검토 출처

확인일: 2026-09-19. 아래는 기능/형식/경계를 확인하기 위한 1차 자료다. 워크플로 자체의 성능 검증을 의미하지 않는다. 공식 형식이 바뀌면 호환 시험과 함께 이 실행기를 갱신한다.

| ID | 출처 | 사용한 범위 |
|---|---|---|
| S1 | https://docs.typesafe.ai/api | HTTP 엔드포인트, request/response, Choice/Score/Noul, 오류 |
| S2 | https://docs.typesafe.ai/models | 모델 ID/별칭·모달리티·언어 안내 |
| S3 | https://docs.typesafe.ai/confidence | 확신도를 워크플로 correctness로 해석하지 않음 |
| S4 | https://docs.typesafe.ai/patterns/fan-out | 같은 요청의 질문은 독립적, 답의 순차 의존은 별도 요청 |
| S5 | https://raw.githubusercontent.com/typesafe-ai/skills/main/skills/typesafe-ai/SKILL.md | 후보 기반 판단, 근거 선정, 스킬 설계 |
| S6 | https://developers.openai.com/codex/skills/ | SKILL.md, agents/openai.yaml, 설치 경로, 명시적 호출 |
| S7 | https://raw.githubusercontent.com/NiazMorshed2007/jev-review/main/skills/jev-review/SKILL.md | 코드 리뷰 신호와 진단·검증의 구분. upstream은 Codex 최종 판단이라 delegated 모드와 다름 |
| S8 | https://github.com/dbreunig/building-with-jev-skill | 질문 설계 참고 후보. 재배포 라이선스 미확인으로 원문 미포함 |

외부 원문 두 종은 collection의 vendor에 분리했다. 이 단일 workbench 스킬 ZIP에는 라이선스가 필요한 외부 스킬 본문을 포함하지 않고 위 링크만 둔다. 본 스킬은 새로 작성한 절차다.
