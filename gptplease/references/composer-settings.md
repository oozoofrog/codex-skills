# Configure the Chat or Work composer

Use after [model and reasoning selection](model-selection.md), before every submission. Both surfaces use supported browser UI selection, readback, and Send from the same composer. Native `create_thread` and `send_message_to_thread` currently expose model/effort overrides only for Codex threads; do not assume native ChatGPT submission inherits browser settings.

1. Discover a supported browser and open a fresh composer, or verify the exact requested existing conversation by URL/ID and content. Select Chat or Work through the observed surface control and confirm any requested ChatGPT project. Preserve unrelated drafts and attachments. Do not send a placeholder to create the conversation.
2. Open the actual model submenu. Select the chosen available model, then inspect that model's effort options. A family/Power/Latest preset is not proof of an exact model. The other surface's menu does not establish availability here.
3. Apply the chosen effort after the model because model changes can reset it. Use semantic controls. For a slider, use its documented keyboard behavior and observe the resulting named label; do not infer the level from a remembered index or position, or cross into Ultra merely to discover the range.
4. Close the picker and read the composer summary. If it omits part of the configuration, reopen and verify model and effort separately. Confirm the same surface/destination and any speed setting still match. Already matching values need verification, not toggling.
5. Verify required [file attachments](file-attachments.md), then send once from this exact composer. Keep a settings-only request unsent. On ambiguous Send, inspect that conversation before any retry. Do not switch to native creation to bypass a failed configuration check.

## Chat and Pro

For Chat, inspect the Chat menu and the selected model's actual reasoning labels. Pro may appear as a named final reasoning option. A subscription badge, text saying “use Pro,” or the Work Max/Ultra control does not establish Chat Pro. A visible combined label such as `5.6 Pro` needs the model submenu as well when model identity matters; do not infer a private model ID from it.

Explicit “Astra Pro” requires **Chat + GPT-6 Astra + Pro** before Send. Plain “Chat Pro” uses an appropriate available model supporting Pro. Plain “Chat” uses automatic model and effort selection and can use non-Pro levels. Do not substitute a different model/level for an exact request.

On 2026-09-07 the observed Chat model menu exposed Latest, GPT-5.6 Sol, and GPT-5.5; Astra was absent. Sol Pro completed a Python attachment review, while a later explicit Astra Pro request was kept unsent. These are account/date-specific observations, not permanent availability rules or Astra Pro proof. Reinspect the current menu.

## Work

Enter Work explicitly and inspect its model submenu even when the Power summary already shows a family name. Localized labels such as `높음` can mean High. Inspect effort after the model change and verify the final summary. The observed Work menu on 2026-09-07 exposed Astra, Sol, Terra, Luna, and GPT-5.5; Astra Light/Medium submissions and a Sol High setting change were observed. These observations are not guarantees for every model/effort pair.

## Blockers and timing

If login is needed, let the user authenticate and resume at the same composer. If an app is blocked, try a separately supported browser; do not bypass it with AppleScript, cookies, private endpoints, or the retired runtime. Missing exact settings, required uploads, or failed readback means **configuration blocked, prompt not submitted**. Preserve the prepared request and explain the concrete missing step.

For an existing requested follow-up, configure before that follow-up and confirm receipt. A picker change does not alter an already running submission; do not stop or replay it without a request. Report selected versus observed settings, whether values changed or were reused, delivery status, and any timing limit. Recommendation or native acceptance alone is not configuration evidence.
