# CLI workflow reference

Read only the task-relevant section. These examples reflect the reference LocalAIHub CLI, not a stable cross-version API. Re-read the resolved executable's `--help` before execution. The examples below **run inference**; they are not installation or static-validation commands.

## Discovery and authority

Start with the user's CLI/root, otherwise `command -v ai`, then the resolved executable's `--help`, `status`, and `models`. Keep that same executable and root for the run. If PATH has no matching CLI, inspect the selected root's `bin/ai`. On the reference Mac only, `/Volumes/eyedisk/AI/bin/ai` is another candidate.

Current root resolution is `AIHUB_ROOT` → app-selected `rootPath` in `~/Library/Application Support/Local AI Studio/config.json` → implementation fallbacks. Read only the needed configuration; do not modify it. Confirm the effective root in `ai status`, especially with a global CLI. For an explicitly selected root, a per-command `AIHUB_ROOT="$ROOT" "$AI" status` (and the same environment for generation) avoids changing other sessions. Do not assume a `--root` flag exists.

Authority on this Mac: `/Volumes/eyedisk/AI/LocalAIHub/README.md`, `Sources/AIHubCLI/main.swift`, `Sources/AIHubCore/AIPaths.swift`, and `Sources/AIHubCore/ModelLaunchers.swift` in that checkout. Matching installed launchers help resolve runtime-specific outputs. The older `/Volumes/eyedisk/AI/README.md` may be stale. Those paths identify sources to discover, not prerequisites on every machine. Do not scan weights or copy runtimes into the skill.

## Task routing and output contracts

| Request | Command / installed model | `--output` contract |
| --- | --- | --- |
| Generate image | `image` / Qwen Image 2.1 | File; normally PNG |
| Edit source image | `image-edit --image` / Qwen Image 2.1 | New file; normally PNG |
| Speak text | `tts` / Qwen3-TTS | Directory; `--prefix` identifies produced file(s) |
| Transcribe recording | `transcribe --audio` / Qwen3-ASR | Stem **without** extension; runtime adds selected format |
| Generate video | `video` / Lance-3B | File; normally MP4 |
| Generate song | `music --prompt` / ACE-Step 1.5 | File ending `.wav`, `.flac`, or `.mp3` |
| Translate English → Korean | `translate` / OPUS-MT | UTF-8 `.txt` file |

When output is omitted, current defaults are under the effective root: `Output/Qwen-Image-2.1`, `Output/Audio`, `Output/Video`, `Output/Music`, and `Output/Translation`. Names are timestamped; do not hardcode an old generated filename. Explicit paths may overwrite files: choose a fresh destination or get overwrite permission first.

In these examples, `$AI` is the verified absolute CLI path and `$OUT` is a resolved, writable, fresh task output directory. Resolve `$INPUT_IMAGE`, `$INPUT_AUDIO`, and `$INPUT_TEXT` from user inputs. Examples illustrate alternatives: **do not run this whole page as a batch**. Keep user-selected paths and formats instead of adopting these example filenames.

### Images

For Qwen Image 2.1, check the [current Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) and any separate license applicable to the user's work:

```sh
"$AI" image --prompt 'A ceramic teapot in soft morning light' --width 512 --height 512 --output "$OUT/teapot.png"
"$AI" image-edit --image "$INPUT_IMAGE" --prompt 'Change the background to a sunset beach' --output "$OUT/edited.png"
```

Current generation width/height must be positive multiples of 32. Do not overwrite the reference image. Model readiness or earlier license acceptance does not establish the rights for a different use.

### Speech and transcription

```sh
"$AI" tts --text '안녕하세요.' --model custom-voice --voice Vivian --language Korean --output "$OUT" --prefix greeting
"$AI" tts --text '안녕하세요.' --model voice-design --instruction 'A calm warm narrator' --language Korean --output "$OUT" --prefix designed
"$AI" transcribe --audio "$INPUT_AUDIO" --model 1.7b --language Korean --format srt --output "$OUT/transcript"
```

TTS `clone` uses `--reference-audio PATH --reference-text TEXT`; use only an authorized speaker sample with its exact spoken transcript. A preset voice does not require cloning. ASR supports `1.7b` / lighter `0.6b`, and `txt`, `srt`, `vtt`, `json`. The transcription example expects `transcript.srt`, not `transcript.srt.srt`. For TTS, inspect runtime output and files such as prefix-matching WAVs rather than assuming that `$OUT` itself is an artifact.

### Video

```sh
"$AI" video --prompt 'A red panda surfing on a sunny wave' --resolution 512 --frames 17 --steps 30 --memory-mode parallel --output "$OUT/panda.mp4"
```

Current help lists 5, 9, 13, 17, 21, 25 frames and `parallel|auto|relay` memory modes. Do not imply that this produces a long clip or guarantees fit in memory. Follow current supported values and check measured duration afterward.

### Music

```sh
"$AI" music --prompt 'Warm acoustic indie pop' --lyrics '오늘의 발걸음을 따라' --language ko --duration 30 --output "$OUT/song.wav"
```

This is direct single-song generation, not an HTTP API workflow. MP3 export requires `ffmpeg` on PATH; if missing, report the blocker rather than silently changing the requested format or installing packages. Current duration range is 10–600 seconds, not a recommended default for every machine. Bare `ai music` opens the existing ACE-Step Gradio UI at `127.0.0.1:7860` and stays in the foreground until stopped (Ctrl-C); never use it as a readiness probe. An existing UI may own an active model job.

### Translation

```sh
"$AI" translate --text 'The model is ready to use.' --output "$OUT/translation.txt"
# Alternative for an approved UTF-8 file:
"$AI" translate --input "$INPUT_TEXT" --output "$OUT/document-ko.txt"
```

Supply exactly one of `--text` or `--input`. The installed model is English-to-Korean; do not invent a language flag or claim other directions. Read the written UTF-8 result and review meaning, names, numbers, and omissions rather than treating a nonempty file as a correct translation.

## Verify the result

Use available local tools; no package installation is required by this skill. For a resolved absolute `$FILE`, `test -s "$FILE"` and `file "$FILE"` are useful first checks, not complete validation. Ensure it is a new regular file from this run, not a prior or partial result. The CLI prints its intended output before starting its child process.

- **Image:** `sips -g format -g pixelWidth -g pixelHeight "$FILE"` on macOS, plus an image-view tool. Check that requested edits appear and source content is retained where required.
- **Audio/video:** if available, `ffprobe -v error -show_entries format=format_name,duration:stream=codec_type,codec_name,width,height,sample_rate,channels -of json "$FILE"`. Probe metadata does not prove full decodability or listening quality; decode/play an appropriate sample, inspect video frames, and note any unreviewed portion.
- **Text/subtitles:** read with strict UTF-8 decoding; parse JSON when requested, check SRT/VTT cues and timestamps, and compare transcription against an authorized audio sample when possible. Report uncertainty or omitted listening checks.

On failure, report the attempted operation, exit/error, partial file paths and missing verification. Do not present corrupt/partial output as finished. On success, give the actual file paths, formats, dimensions/duration or text type, selected model/settings, and what was inspected. Do not claim a real attachment unless the delivery surface actually attached the file.
