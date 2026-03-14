# Manual Ralph Loop with Codex

Codex에서는 Claude plugin의 Stop hook 대신 **명시적 shell loop + `codex exec`** 방식이 더 현실적입니다.

## 기본 패턴
```bash
PROMPT_FILE=.tmp/ralph-prompt.md
MAX_ITERS=10

for i in $(seq 1 "$MAX_ITERS"); do
  echo "=== iteration $i/$MAX_ITERS ==="
  codex exec --sandbox workspace-write --ask-for-approval never -C "$PWD" - < "$PROMPT_FILE"
  # 여기서 테스트/grep/검증 명령을 넣고 종료 여부 판단
  # 성공하면 break
  # 실패하면 다음 iteration 진행
 done
```

## completion phrase 사용 예시
```bash
PROMPT_FILE=.tmp/ralph-prompt.md
LAST=.tmp/ralph-last.txt
MAX_ITERS=8

for i in $(seq 1 "$MAX_ITERS"); do
  codex exec --sandbox workspace-write --ask-for-approval never -C "$PWD" \
    -o "$LAST" - < "$PROMPT_FILE"

  if grep -q '<promise>COMPLETE</promise>' "$LAST"; then
    echo "done on iteration $i"
    break
  fi
 done
```

## 추천 사항
- 루프 안에서 테스트/빌드/grep 같은 외부 검증을 같이 두기
- 각 iteration 결과를 파일에 남기기
- 실패해도 다음 iteration이 무엇을 봐야 하는지 prompt에 명시하기
