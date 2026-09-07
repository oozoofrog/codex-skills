# Task handoff

## Compose the prompt

Adapt this outline to the user's task; omit empty sections instead of requiring every field. Preserve the user's requested format and level of detail.

```text
목표: [완료해야 할 구체적인 일]
배경과 자료: [이 작업에 필요한 사실, 사용자가 전달하려는 자료 또는 접근 가능한 링크]
산출물: [문서·분석·표·초안 등 형식과 독자]
조건: [언어, 범위, 제외 사항, 사용자가 정한 제약]
완료 기준: [결과에서 확인할 수 있어야 하는 항목]
```

Do not copy the entire local conversation by default. Include relevant decisions and known facts, separate uncertainties, and keep quoted source material distinct from instructions. Do not add Deep research, a paid tool, a new deadline, or a specific model merely to make the prompt more elaborate. A request to investigate or compare can ask Work to support material claims with sources without promising that a particular connector is available there.

Example user request:

> $gptwork 한국어 학습 앱의 첫 사용자 안내를 개선하는 기획 작업을 ChatGPT Work에 만들어 주세요. 대상은 성인 초보자이고, 결과는 1페이지 제안서로 받고 싶습니다.

The default delivery is the verified Work UI composer. Complete [model selection](model-selection.md) before typing/submitting the final prompt. The following native target is only for an explicit current/default-settings opt-out, not the normal creation path:

```json
{"target": {"type": "chatgptWorkCloud"}}
```

For that opt-out, pass the self-contained `prompt`, optional `title`, and resolved ChatGPT `projectId` when requested; omit Codex-only `model`/`thinking`. State that native submission does not verify model or effort. Never use this exception simply because UI configuration is inconvenient or unavailable.

## Destination and inputs

The current native tool contract supports a projectless cloud task or a ChatGPT project returned by `list_projects`. It has no local-file upload argument for this target. Do not pretend that a filesystem path, project ID, or link guarantees access to source content. For actual file delivery, use the supported browser upload route in [file attachments](file-attachments.md); the native target limitation does not imply that Work UI cannot attach files. If essential material cannot be delivered through any available supported route, report the missing capability and preserve the prepared request. Do not upload to another service to manufacture a link.

If a required project cannot be resolved, continue preparing the prompt while asking for the exact project or permission to use a projectless destination. Do not choose the current repository as a cloud project automatically.

The tool's `model` and `thinking` fields are for Codex tasks and must be omitted for ChatGPT Work. Native creation does not guarantee Pro, a particular reasoning effort, speed, account entitlement, or tools in the new task. For mandatory automatic pre-submission configuration, follow [model selection](model-selection.md). An exact setting must not be moved into a prompt as if it were configuration.

## Creation, recovery, and follow-up

- Report creation from the actual tool response, including pending or attention-needed states. Do not report that research, writing, or analysis has completed just because the task exists.
- If creation is definitively rejected before a task exists, report the reason and retain the prepared prompt. Retry only after the relevant input or availability changes.
- If the result is uncertain, inspect `list_threads` and candidate `read_thread` results for the matching initial request and destination. A matching title alone is insufficient proof. Reuse a confirmed task; when uncertainty remains, explain it and do not automatically resend.
- Use an actual returned `threadId` for native reads, opening, or a requested follow-up. Do not pass a pending `clientThreadId` where `threadId` is required. Do not assume Codex-only waiting/automation tools support a ChatGPT Work task.
- For an existing Work task, verify its identity, configure the same composer, and send the requested follow-up once. On uncertainty, inspect recent messages for that exact follow-up and report unresolved delivery rather than resending. Native follow-up is restricted to the same explicit default-settings opt-out as native creation. After delivery, wait for the completed response and process it in the invoking session under [response return](response-return.md). Do not schedule unattended monitoring or send unsolicited follow-ups.

This reference reflects the available Codex app tool schema, not a public compatibility promise. Check the live tool contract when executing the skill; a missing capability is a limitation to report, not permission to invent another channel.
