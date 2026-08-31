# Operational workflow

```text
desktop-doctor
  -> consult / prepare Schema 4
  -> verify
  -> exact or standing approval
  -> mcp-activate
  -> desktop-plan
  -> visible ChatGPT app Send once
  -> collect submission
  -> collect next completed response
  -> mcp-stop / audit verification
  -> import-response
  -> record-evaluation
```

`desktop-doctor`, `verify`, `diagnostic-status`, `desktop-plan`은 prompt를 보내지 않습니다. `mcp-activate`도 Send가 아닙니다. 실제 전송은 visible ChatGPT app UI에서 한 번만 일어나며, `collect`가 증거를 검증한 뒤에만 state가 submitted로 이동합니다.

Delivery channel을 바꾸는 fallback은 없습니다. Desktop UI capability가 없거나 account/app/model이 모호하면 package를 보존하고 사람 checkpoint로 멈춥니다.
