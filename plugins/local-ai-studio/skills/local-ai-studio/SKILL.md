---
name: local-ai-studio
description: Set up and use Local AI Studio on Apple Silicon when the user requests LocalAIHub or on-device model work for image, speech, video, music, or English-to-Korean translation. Install only the needed model group when absent and verify results. Do not install it for generic media requests or use it for unrelated AI development; respect a user-selected tool.
---

# Local AI Studio

Complete the user's requested Local AI Studio or on-device model task. If LocalAIHub or the required model group is absent, install that prerequisite using [setup guidance](references/setup.md), then continue the same task. Do not start a large local installation for a generic media request. User-selected tools, models, output locations, and formats take precedence; do not silently substitute this CLI, a cloud service, or another model.

## Discover before running

- Resolve the user's executable first, otherwise inspect `command -v ai`. Confirm it is Local AI Studio with `ai --help` before using it; an unrelated executable named `ai` is not sufficient. Read current top-level help for every new task; do not assume subcommand `--help` is supported.
- Find the selected storage root from `AIHUB_ROOT`, the app's configuration, and `ai status`; then inspect `ai models`. On the reference Mac, `/Volumes/eyedisk/AI/bin/ai` and `/Volumes/eyedisk/AI/LocalAIHub/README.md` are discovery candidates only, not defaults for other machines. If a configured volume is missing, preserve that choice rather than creating a replacement root.
- Prefer the installed CLI, matching LocalAIHub README and current code over the older parent AI README, especially for music and translation. Read [command/output details](references/cli-workflows.md) for the selected modality. If LocalAIHub or the needed group is missing, follow [setup guidance](references/setup.md). If the fetched version lacks the requested command, report the version mismatch instead of claiming support.
- `READY` checks required local files, not successful inference, output quality, or even every runtime dependency. Check the relevant group's readiness without running an extra generation as a probe.

## Execute the requested task

1. Resolve input files and the requested deliverable. Treat user-provided inputs as authorized for the requested operation unless there is a concrete reason to doubt it. Voice cloning needs an authorized speaker sample and its exact transcript. Keep inputs local. Check applicable model terms: the current Qwen Image 2.1 public license allows non-commercial research or evaluation; for commercial use, check whether the user has a separate license before running it.
2. Select the matching command from current help. Translation here is English → Korean, not arbitrary language pairs. `ai music --prompt ...` creates one song without a server; bare `ai music` opens a persistent Gradio UI, so use it only when a UI is requested.
3. Resolve an absolute output destination before launch. Preserve user paths/formats, check writable space and existing files, and avoid overwriting sources or prior outputs without permission. If unspecified, use the selected root's output folders and unique names. `--output` is a **directory for TTS**, a **stem for transcription**, and a **file path for the other generators/translation**. Unsupported formats need an agreed conversion, not a renamed extension.
4. On a 24 GB Mac, run only one large generator at a time, including other CLI/app/UI sessions. Check for active jobs; wait or coordinate rather than killing unrelated work. Keep a requested size/duration; where unspecified, start with a modest deliverable. Video `--memory-mode parallel` is an internal mode, not permission for concurrent model jobs.
5. Pass prompts, lyrics and paths as safely quoted arguments or an argument array, never shell-evaluated user text. Capture the command/settings, exit status and actual output locations; wait for completion. If a run fails, inspect the error and any partial output before a bounded retry. On OOM, missing runtime, or unresponsive execution, stop and report; do not loop, download/reinstall, or launch duplicates automatically.

## Verify and deliver

- A printed `Output:` line is an intended destination emitted **before** inference, not proof of success. Require a completed run plus newly written, nonempty files tied to that run. For TTS, enumerate actual files in the chosen directory/prefix; do not hand back only a directory or assume a filename.
- Check actual file format/decodability, not just extension. Inspect image dimensions and preview; inspect audio/video duration, streams and playable samples; read UTF-8 translation/transcription and validate the requested subtitle/JSON structure. Compare content to the request where tools allow. Use [verification examples](references/cli-workflows.md#verify-the-result) as needed.
- Report readiness, process completion, file/format checks, and visual/listening/semantic review separately. If playback or viewing is unavailable, say so; never infer quality from `READY` or exit code alone.
- Deliver the verified files with usable paths/links (or real attachments when supported), key settings and any limitations. A path is not an attachment. Keep model weights, environments, generated media, private logs and credentials out of this skills repository.
