# Result Ledger Template

연속 연구는 **누적 비교 가능한 기록**이 핵심입니다.

## Minimal markdown table

```md
| round | hypothesis | change | hard gates | metric | status | notes |
|---|---|---|---|---|---|---|
| 0 | baseline | none | pass | ... | keep | baseline |
| 1 | ... | ... | pass/fail | ... | keep/discard/crash | ... |
```

## TSV template

탭 구분 형식을 쓰면 후처리가 쉽습니다.

```text
round	hypothesis	change	hard_gates	metric	status	notes
0	baseline	none	pass	...	keep	baseline
1	...	...	pass	...	discard	...
```

## Status vocabulary

- `keep` — 현재 best state로 채택
- `discard` — baseline 또는 직전 best보다 못함
- `crash` — 실행 실패 또는 가설 붕괴
- `pivot` — 접근 방향 전환
- `stop` — 종료

## End-of-loop summary

마지막에는 아래를 꼭 남깁니다.

```md
## Final summary
- objective:
- best state:
- biggest gain:
- failed lines of inquiry:
- remaining risks:
- next recommended experiment:
```
