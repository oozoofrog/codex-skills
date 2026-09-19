# 세션 인계

원본 로그를 매번 컨텍스트에 넣지 않고 기존 `session-continuity` 작업 기록에 다음만 병합한다. 기존 상태 파일을 덮어쓰지 않는다.

```text
task_id:
Jev mode: delegated / advisory / evaluation
workflow:
packet_sha256:
run directory:
origin: live / fixture / external
current choice and decision_status:
policy revision:
watched scope and freshness at implementation start:
actual validation performed:
unverified claims / unresolved evidence:
next concrete action:
```

새 세션은 `status`, 필요한 경우 `check`와 실제 Git/테스트 상태를 확인한다. 이전 receipt를 본 것만으로 현 코드가 검증됐다고 말하지 않는다. 실행 시작 전의 freshness와 구현 이후의 산출물 검증을 구분한다.

`gptplease`는 추가 설명·자료·반례를 얻는 보조 경로다. 사용자가 승인한 전송 범위를 유지한다. 상담 답변으로 Jev의 최종 선택을 조용히 바꾸지 말고 새 증거로 표시해 lineage에 연결한다.
