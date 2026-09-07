# Task handoff

Prepare a self-contained prompt for the selected Chat or Work route. Adapt this outline and omit empty sections:

```text
목표: [완료할 일]
배경과 자료: [필요한 사실, 승인된 첨부 파일의 역할]
산출물: [답변·검토·수정안·문서 등]
조건: [언어, 범위, 제외 사항, 시간·비용 제한]
완료 기준: [결과에서 확인할 항목]
```

Do not copy the entire local conversation by default. Include relevant decisions and known facts, distinguish uncertainties, and keep quoted source or file content separate from instructions. Do not add Deep research, a paid tool, or a new deadline merely to elaborate the request.

For code reviews, select the minimum relevant files and requested diff scope from current source. Include necessary companion context, but never infer whole-repository disclosure. If the request requires an exact code snapshot, prepare and inspect that snapshot before sending. This skill does not implement the removed runtime's automatic secret scan, immutable package approval, or receipt verification; do not claim those checks occurred. Follow existing user disclosure constraints and resolve detected sensitive content before delivery.

## Destination and files

- Resolve a named ChatGPT project through available project listing and its actual UI destination. Do not substitute a same-named local/Git project. With no project request, use a projectless composer.
- For an existing conversation, verify its actual URL/ID and contents. Its Chat/Work surface takes precedence over the default for new work. Configure before any requested follow-up and preserve the known conversation rather than creating another one.
- Use [file attachments](file-attachments.md) for actual uploads. Native `create_thread` has no attachment parameter for this route; that does not imply browser upload is unavailable. A path or external link alone does not prove that ChatGPT can access its contents.
- If a required project, file, or setting cannot be resolved, continue independent prompt preparation while resolving the one missing input. Preserve the draft; do not submit an incomplete request as a fallback.

## Submission and recovery

Use the same verified browser composer for submission. Native `create_thread`/`send_message_to_thread` model overrides are Codex-only and cannot establish the requested Chat/Work settings for a particular send. Use supported `list_threads`/`read_thread` for identity and response retrieval; do not use the creation/send tools as a fallback.

Send once and confirm the received prompt and attachments. If Send times out or success is ambiguous, inspect that exact conversation for receipt; do not repeat the action automatically. Use only observed real conversation IDs for thread reads, never a temporary/pending client ID. A title alone is insufficient identity.

Creation/receipt is an intermediate state. After delivery, wait for the completed assistant turn and process it in the invoking session under [response return](response-return.md). A new task is not needed to bring the answer back. Do not schedule unattended monitoring or send additional prompts unless requested.

Examples:

```text
$gptplease Chat Pro로 선택한 파일의 버그를 검토하고 답변을 여기서 확인해주세요.
$gptplease Work에서 Astra로 이 기획안을 분석하고 완료 결과를 가져와 주세요.
```
