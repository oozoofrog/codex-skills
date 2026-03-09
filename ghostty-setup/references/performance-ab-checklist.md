# Ghostty 성능 A/B 점검안

## 목적

`background-blur` 자체 비용과, 대량 출력이 Ghostty에 주는 부담을 분리해서 보기.
이번 점검의 목적은 “Ghostty가 node 폭증의 원인인가”를 추정하는 것이 아니라, **Ghostty 렌더링 비용이 증상을 얼마나 증폭하는지**를 분리 측정하는 것이다.

## 준비

1. 다른 장시간 실행 중인 AI 세션을 최대한 정리하기.
2. 같은 Mac, 같은 디스플레이, 같은 Ghostty 창 크기로 비교하기.
3. 비교 중에는 theme, font, opacity 외 다른 설정을 건드리지 않기.
4. 각 케이스 실행 전후로 아래 값을 기록하기.

## 기록 명령

Ghostty RSS:

```bash
ps -axo rss,command | awk '/Ghostty.app\\/Contents\\/MacOS\\/ghostty/ {sum+=$1} END {printf("ghostty_rss_kb=%d\\n", sum)}'
```

Codex/Claude/node 계열 RSS:

```bash
ps -axo rss,command | awk '/node \\/opt\\/homebrew\\/bin\\/codex|\\/codex\\/codex -s danger-full-access -a never|firebase mcp|playwright-mcp|xcodebuildmcp mcp|\\.local\\/bin\\/claude/ {sum+=$1; count+=1} END {printf("node_like_count=%d node_like_rss_kb=%d\\n", count, sum)}'
```

## Phase 1: Ghostty 단독 렌더링 영향

### A1. Blur ON + 저출력

- 현재 설정 유지 (`background-blur = true`)
- 새 Ghostty 창에서 아래 실행:

```bash
printf 'ghostty-ab-low-output\n'
```

- 전후 RSS 기록

### A2. Blur OFF + 저출력

- `background-blur = false`로 바꾸고 Ghostty 재시작
- 같은 명령 실행:

```bash
printf 'ghostty-ab-low-output\n'
```

- 전후 RSS 기록

### B1. Blur ON + 고출력

- `background-blur = true`
- 새 Ghostty 창에서 아래 실행:

```bash
yes "ghostty-ab-high-output" | head -n 200000
```

- 완료 직후 RSS 기록

### B2. Blur OFF + 고출력

- `background-blur = false`
- 같은 명령 실행:

```bash
yes "ghostty-ab-high-output" | head -n 200000
```

- 완료 직후 RSS 기록

## Phase 2: 동일 작업, 터미널 출력 유무 비교

이 단계는 Ghostty가 아니라 **출력 스트리밍 자체**가 부담인지 확인한다.
가능하면 같은 작업을 다음 두 조건으로 비교한다.

### C1. 동일 작업 + 터미널로 그대로 출력

- 평소처럼 Ghostty 화면에 출력이 계속 보이게 실행하기.

### C2. 동일 작업 + 파일로 리다이렉트

- 가능한 경우 stdout/stderr를 파일로 보내기.
- 예:

```bash
some-noisy-command > /tmp/ghostty-ab.log 2>&1
```

### 판정 기준

- `C1`에서만 Ghostty RSS가 크게 증가하면:
  - 터미널 렌더링/스크롤백 영향이 큼
- `C1`, `C2` 모두 node-like RSS와 프로세스 수가 비슷하게 증가하면:
  - Ghostty보다 런타임/에이전트 fan-out 영향이 큼
- `B1`만 유독 높고 `B2`가 확 낮으면:
  - `background-blur`가 증폭 요인임
- `B1`, `B2`가 둘 다 높고 `A1`, `A2`는 낮으면:
  - blur보다 대량 출력/scrollback 영향이 큼

## 권장 해석 순서

1. Ghostty-only A/B로 렌더링 비용을 먼저 확인하기.
2. 그 다음 실제 AI 작업에서 출력 유무 비교로 터미널 기여도를 보기.
3. 마지막으로 node-like 프로세스 수가 계속 늘면 Ghostty가 아니라 런타임 쪽으로 결론 내리기.

## 즉시 적용 가능한 보수적 설정

원인 분리가 끝나기 전까지는 다음을 권장한다.

- `background-blur = false`
- 대량 출력 명령은 가능하면 파일 리다이렉트 또는 로그 파일로 우회
- 장시간 AI 세션은 동시에 여러 개 띄우지 않기
