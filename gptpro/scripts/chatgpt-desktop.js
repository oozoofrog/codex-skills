#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
const readline = require("node:readline");
const { PrivateConversationClient } = require("../runtime/chatgpt-desktop/conversation-client.js");
const { sanitizedError, runtimeError } = require("../runtime/chatgpt-desktop/errors.js");

const MAX_PROMPT_BYTES = 256 * 1024;

function usage() {
  return `usage: chatgpt-desktop.js <probe|models|ask|collect> [options]

Private macOS ChatGPT Desktop runtime (Node 22+; no npm install).

  probe [--endpoint http://127.0.0.1:9223]
  models [--endpoint ...]
  ask --events-jsonl --prompt-file FILE --model BACKEND_ID [--thinking-effort VALUE]
      [--system-prompt-file FILE]
      [--history-mode normal] [--timeout-seconds N]
  collect --events-jsonl --prompt-file FILE --message-id UUID [--timeout-seconds N]

The ask command sends one bounded inline user message, never enables tools, and
never edits repository files. The collect command performs authenticated GET
readback only and never sends a conversation message.`;
}

function parse(argv) {
  const command = argv.shift();
  const result = { command };
  while (argv.length) {
    const token = argv.shift();
    if (!token.startsWith("--")) throw runtimeError("ARGUMENT_ERROR", `Unexpected argument: ${token}`);
    const name = token.slice(2).replaceAll("-", "_");
    if (["json", "help", "events_jsonl"].includes(name)) result[name] = true;
    else {
      if (!argv.length) throw runtimeError("ARGUMENT_ERROR", `Missing value for ${token}`);
      result[name] = argv.shift();
    }
  }
  const allowed = {
    probe: new Set(["command", "endpoint", "json", "help"]),
    models: new Set(["command", "endpoint", "json", "help"]),
    ask: new Set(["command", "endpoint", "prompt_file", "system_prompt_file", "model", "thinking_effort", "history_mode", "timeout_seconds", "message_id", "events_jsonl", "json", "help"]),
    collect: new Set(["command", "endpoint", "prompt_file", "timeout_seconds", "message_id", "not_before", "events_jsonl", "json", "help"]),
  }[command];
  if (!allowed) throw runtimeError("ARGUMENT_ERROR", `Unknown command: ${command ?? ""}`);
  const unknown = Object.keys(result).find((name) => !allowed.has(name));
  if (unknown) throw runtimeError("ARGUMENT_ERROR", `Unsupported option: --${unknown.replaceAll("_", "-")}`);
  return result;
}

function readText(file, label, maximum = MAX_PROMPT_BYTES) {
  return readTextArtifact(file, label, maximum).text;
}

function readTextArtifact(file, label, maximum = MAX_PROMPT_BYTES) {
  if (!file) throw runtimeError("ARGUMENT_ERROR", `${label} is required.`);
  const bytes = fs.readFileSync(path.resolve(file));
  if (bytes.length > maximum) throw runtimeError("INLINE_CONTEXT_LIMIT_EXCEEDED", `${label} exceeds the fixed ${maximum}-byte limit.`);
  let value;
  try { value = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
  catch (cause) { throw runtimeError("ARGUMENT_ERROR", `${label} must be strict UTF-8.`, { cause }); }
  if (!value.trim()) throw runtimeError("ARGUMENT_ERROR", `${label} must not be empty.`);
  return { text: value, bytes: bytes.length, sha256: crypto.createHash("sha256").update(bytes).digest("hex") };
}

async function waitForDispatchAuthorization(dispatchToken, signal, timeoutMs = 30_000) {
  if (signal?.aborted) throw signal.reason ?? runtimeError("CANCELLED", "Dispatch authorization was cancelled.");
  const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      input.close();
      callback(value);
    };
    const abort = () => finish(reject, signal.reason ?? runtimeError("CANCELLED", "Dispatch authorization was cancelled."));
    const timer = setTimeout(
      () => finish(reject, runtimeError("DISPATCH_AUTHORIZATION_TIMEOUT", "The parent did not authorize the prepared dispatch.")),
      timeoutMs,
    );
    signal?.addEventListener("abort", abort, { once: true });
    input.once("line", (line) => {
      let value;
      try { value = JSON.parse(line); } catch {
        finish(reject, runtimeError("DISPATCH_AUTHORIZATION_INVALID", "The parent dispatch authorization was invalid."));
        return;
      }
      if (value?.type !== "dispatch_authorized" || value?.dispatch_token !== dispatchToken) {
        finish(reject, runtimeError("DISPATCH_AUTHORIZATION_INVALID", "The parent dispatch authorization did not match this request."));
        return;
      }
      finish(resolve);
    });
    input.once("close", () => {
      if (!settled) finish(reject, runtimeError("DISPATCH_AUTHORIZATION_MISSING", "The parent closed before authorizing dispatch."));
    });
  });
}

function emit(value, jsonl = false) {
  process.stdout.write(`${JSON.stringify(value, null, jsonl ? 0 : 2)}\n`);
}

async function main(argv = process.argv.slice(2), dependencies = {}) {
  if (!argv.length || argv[0] === "--help" || argv[0] === "-h") { process.stdout.write(`${usage()}\n`); return 0; }
  const options = parse([...argv]);
  if (options.help) { process.stdout.write(`${usage()}\n`); return 0; }
  if (!process.versions.node || Number(process.versions.node.split(".")[0]) < 22) throw runtimeError("NODE_VERSION_UNSUPPORTED", "Node 22 or newer is required.");
  const client = dependencies.client ?? new PrivateConversationClient({ endpoint: options.endpoint });
  const controller = new AbortController();
  const stop = () => controller.abort();
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  try {
    if (options.command === "probe") emit(await client.probe());
    else if (options.command === "models") emit(await client.models({ signal: controller.signal }));
    else if (options.command === "ask" || options.command === "collect") {
      if (!options.events_jsonl) throw runtimeError("ARGUMENT_ERROR", `${options.command} is an internal governed command; use gptpro.py ${options.command === "ask" ? "consult" : "collect-response"}.`);
      const promptArtifact = readTextArtifact(options.prompt_file, "--prompt-file");
      const prompt = promptArtifact.text;
      const timeoutSeconds = Number(options.timeout_seconds ?? 2700);
      if (!Number.isFinite(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 3600) throw runtimeError("ARGUMENT_ERROR", "--timeout-seconds must be between 1 and 3600.");
      if (options.command === "collect" && !options.message_id) {
        throw runtimeError("ARGUMENT_ERROR", "collect requires --message-id from the governed package.");
      }
      const messageId = options.message_id ?? crypto.randomUUID();
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(messageId)) {
        throw runtimeError("ARGUMENT_ERROR", "--message-id must be a canonical UUID.");
      }
      let result;
      if (options.command === "collect") {
        const notBeforeMs = options.not_before ? Date.parse(options.not_before) : Date.now();
        if (!Number.isFinite(notBeforeMs)) throw runtimeError("ARGUMENT_ERROR", "--not-before must be an ISO-8601 timestamp.");
        result = await client.collect({
          prompt,
          messageId,
          notBeforeMs,
          signal: controller.signal,
          timeoutMs: timeoutSeconds * 1000,
          onProgress: (event) => emit(event, true),
        });
      } else {
        if (!options.model) throw runtimeError("ARGUMENT_ERROR", "--model is required.");
        const systemArtifact = options.system_prompt_file
          ? readTextArtifact(options.system_prompt_file, "--system-prompt-file", 64 * 1024)
          : { text: "", bytes: 0, sha256: crypto.createHash("sha256").update("").digest("hex") };
        const systemPrompt = systemArtifact.text;
        const historyMode = options.history_mode ?? "normal";
        if (historyMode !== "normal") throw runtimeError("ARGUMENT_ERROR", "--history-mode must be normal for Schema-6 inline consultations.");
        const selected = await client.resolveModel(options.model, options.thinking_effort, {
          signal: controller.signal,
          timeoutMs: Math.min(timeoutSeconds * 1000, 30_000),
        });
        const dispatchToken = crypto.randomUUID();
        let dispatchPrepared = false;
        result = await client.run({
          prompt, systemPrompt, modelId: selected.id, effort: selected.thinking_effort,
          messageId,
          signal: controller.signal, historyMode,
          timeoutMs: timeoutSeconds * 1000,
          onBeforeSubmit: async () => {
            if (dispatchPrepared) throw runtimeError("DESKTOP_RUNTIME_PROTOCOL_ERROR", "Dispatch preparation ran more than once.");
            dispatchPrepared = true;
            emit({
              type: "dispatch_ready",
              dispatch_token: dispatchToken,
              prompt_sha256: promptArtifact.sha256,
              prompt_bytes: promptArtifact.bytes,
              system_prompt_sha256: systemArtifact.sha256,
              state_sha256: null,
              backend_model_id: selected.id,
              thinking_effort: selected.thinking_effort ?? null,
              history_mode: historyMode,
              message_id: messageId,
            }, true);
            const authorize = dependencies.authorizeDispatch ?? waitForDispatchAuthorization;
            await authorize(dispatchToken, controller.signal);
          },
          onEvent: (event) => emit(event, true),
          onProgress: (event) => emit(event, true),
        });
      }
      const complete = { type: "complete", ...result };
      emit(complete, true);
    }
    return 0;
  } finally {
    process.removeListener("SIGINT", stop);
    process.removeListener("SIGTERM", stop);
    await client.close();
  }
}

if (require.main === module) {
  main().then((code) => { process.exitCode = code; }).catch((error) => {
    process.stderr.write(`${JSON.stringify({ ok: false, error: sanitizedError(error) })}\n`);
    process.exitCode = error?.code === "ARGUMENT_ERROR" ? 2 : 3;
  });
}

module.exports = {
  main,
  parse,
  readText,
  readTextArtifact,
  usage,
  waitForDispatchAuthorization,
};
