# State Snapshot and Handoff

장기 연구 루프는 ledger만으로 충분하지 않습니다. 다음 세션이 바로 이어받을 수 있도록 **현재 상태 요약**을 별도로 남겨야 합니다.

## 언제 필요한가

- `guided-loop`가 여러 라운드로 이어질 때
- `autonomous-loop`를 시작할 때
- 같은 objective로 나중에 다시 들어올 가능성이 있을 때

한 번성 `design` 작업이면 생략할 수 있지만, best-known state가 생기는 순간부터는 유지하는 편이 안전합니다.

## Minimal template

```md
## State Snapshot
- objective:
- mode:
- baseline:
- best-known state:
- current active hypothesis:
- most recent experiment status:
- most recent control action:
- open risks:
- next candidate hypotheses:
- handoff notes:
```

## Update rules

매 라운드가 끝날 때 최소 아래를 갱신합니다.

1. 현재 **best-known state**
2. 직전 라운드의 **experiment status**와 **control action**
3. 지금 열려 있는 **가설 1개**
4. 다음 후보 **1~3개**
5. 즉시 중단해야 하는 **리스크**

## Handoff discipline

- “무엇을 많이 했다”보다 **다음 세션이 무엇부터 해야 하는지**를 남깁니다.
- 이미 버린 가설군은 이유와 함께 적어 중복 실험을 막습니다.
- 새 mutable surface를 열어야 한다면 그대로 진행하지 말고 `rescope` 또는 `escalate`로 기록합니다.
