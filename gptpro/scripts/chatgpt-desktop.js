#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { connectDesktopRuntime } = require("../runtime/chatgpt-desktop");
const { DEFAULT_ENDPOINT, DEFAULT_TARGET_URL } = require("../runtime/chatgpt-desktop/cdp-client");
const { DesktopRuntimeError, asRuntimeError, errorPayload } = require("../runtime/chatgpt-desktop/errors");

const COMMANDS = new Set(["probe", "models", "ask"]);

function usage() {
  return `Usage:
  chatgpt-desktop.js probe [--endpoint URL] [--timeout-ms N]
  chatgpt-desktop.js models [--endpoint URL] [--timeout-ms N]
  chatgpt-desktop.js ask --handoff-dir DIR --prompt-file PATH --model ID --output PATH [options]

Ask options:
  --handoff-dir DIR           Approved gptpro handoff verified before any Desktop connection
  --package-id ID             Package identity used for deterministic response markers
  --manifest-sha256 HASH      Approved manifest hash recorded in the result receipt
  --prompt-sha256 HASH        Expected prompt hash; mismatch fails before submission
  --thinking-effort EFFORT    Exact live-catalog effort; unsupported values fail closed
  --raw-output PATH           Raw captured assistant turn (default: <output>.raw.md)
  --result-file PATH          Machine-readable submission result (default: <output>.result.json)
  --timeout-ms N              Positive timeout in milliseconds (default: 120000)
  --endpoint URL              Loopback CDP discovery endpoint (default: ${DEFAULT_ENDPOINT})
  --target-url URL            Must remain the exact renderer target ${DEFAULT_TARGET_URL}

This runtime never logs in, reads cookies/tokens, calls local tools, changes repositories,
or launches/kills ChatGPT. A successful probe is not approval to run ask.`;
}

function parseArgs(argv) {
  if (!argv.length || argv.includes("--help") || argv.includes("-h")) return { help: true };
  const command = argv[0];
  if (!COMMANDS.has(command)) throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", `Unknown command: ${command}`);
  const options = { command, endpoint: DEFAULT_ENDPOINT, targetUrl: DEFAULT_TARGET_URL, timeoutMs: 120000 };
  for (let index = 1; index < argv.length; index += 1) {
    const flag = argv[index];
    if (!flag.startsWith("--")) throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", `Unexpected argument: ${flag}`);
    const value = argv[++index];
    if (value == null || value.startsWith("--")) throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", `Missing value for ${flag}`);
    const key = {
      "--endpoint": "endpoint", "--target-url": "targetUrl", "--timeout-ms": "timeoutMs",
      "--prompt-file": "promptFile", "--model": "model", "--thinking-effort": "thinkingEffort",
      "--handoff-dir": "handoffDir",
      "--output": "output", "--raw-output": "rawOutput", "--result-file": "resultFile",
      "--package-id": "packageId", "--manifest-sha256": "manifestSha256", "--prompt-sha256": "expectedPromptSha256",
    }[flag];
    if (!key) throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", `Unknown option: ${flag}`);
    options[key] = key === "timeoutMs" ? Number(value) : value;
  }
  if (!Number.isSafeInteger(options.timeoutMs) || options.timeoutMs <= 0) {
    throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", "--timeout-ms must be a positive integer");
  }
  if (options.targetUrl !== DEFAULT_TARGET_URL) {
    throw new DesktopRuntimeError("TARGET_NOT_FOUND", `Phase 1 requires the exact renderer target ${DEFAULT_TARGET_URL}`);
  }
  return options;
}

function sha256(value) { return crypto.createHash("sha256").update(value).digest("hex"); }

function readPrompt(promptFile) {
  if (!promptFile) throw new DesktopRuntimeError("CONVERSATION_REJECTED", "ask requires --prompt-file");
  let prompt;
  try { prompt = fs.readFileSync(path.resolve(promptFile), "utf8"); }
  catch (error) { throw new DesktopRuntimeError("CONVERSATION_REJECTED", `Unable to read prompt file: ${error.message}`); }
  if (!prompt.trim()) throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Prompt file must not be empty");
  return prompt;
}

function packageIdFrom(prompt, explicit) {
  if (explicit) return explicit;
  const matches = [...prompt.matchAll(/^Package:\s*`([^`]+)`\s*$/gm)];
  if (matches.length !== 1) throw new DesktopRuntimeError("CONVERSATION_REJECTED", "ask requires --package-id or exactly one Package line in the prompt");
  return matches[0][1];
}

function assertHash(value, label) {
  if (value != null && !/^[0-9a-f]{64}$/.test(value)) throw new DesktopRuntimeError("CONVERSATION_REJECTED", `${label} must be a lowercase SHA-256 value`);
}

function loadAuthorization(options, spawnSync = childProcess.spawnSync) {
  if (options.authorization) return options.authorization;
  if (!options.handoffDir) throw new DesktopRuntimeError("CONVERSATION_REJECTED", "ask requires --handoff-dir for package-specific approval verification");
  const governanceScript = path.join(__dirname, "gptpro.py");
  const result = spawnSync("python3", [governanceScript, "desktop-authorization", "--handoff-dir", path.resolve(options.handoffDir)], {
    encoding: "utf8",
    maxBuffer: 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    throw new DesktopRuntimeError("CONVERSATION_REJECTED", "gptpro governance did not authorize this Desktop request");
  }
  let authorization;
  try { authorization = JSON.parse(result.stdout); }
  catch { throw new DesktopRuntimeError("CONVERSATION_REJECTED", "gptpro governance returned invalid Desktop authorization"); }
  if (authorization.authorized !== true || authorization.phase !== "approved" ||
      authorization.delivery_channel !== "desktop-cdp" || authorization.tools_enabled !== false ||
      typeof authorization.model_id !== "string" || !authorization.model_id ||
      (authorization.thinking_effort != null && typeof authorization.thinking_effort !== "string")) {
    throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Desktop authorization is incomplete or invalid");
  }
  return authorization;
}

function atomicWrite(filePath, data, { exclusive = false } = {}) {
  const resolved = path.resolve(filePath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  const temporary = path.join(path.dirname(resolved), `.${path.basename(resolved)}.${process.pid}.${crypto.randomUUID()}.tmp`);
  try {
    fs.writeFileSync(temporary, data, { encoding: "utf8", mode: 0o600, flag: "wx" });
    if (exclusive) {
      fs.linkSync(temporary, resolved);
      fs.unlinkSync(temporary);
    } else {
      fs.renameSync(temporary, resolved);
    }
  } finally {
    try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== "ENOENT") throw error; }
  }
  return resolved;
}

function outputTargets(options, handoffDir) {
  const handoff = path.resolve(handoffDir);
  const output = path.resolve(options.output);
  const rawOutput = path.resolve(options.rawOutput || `${output}.raw.md`);
  const resultFile = path.resolve(options.resultFile || `${output}.result.json`);
  const targets = [output, rawOutput, resultFile];
  if (new Set(targets).size !== targets.length || targets.some((target) => path.dirname(target) !== handoff)) {
    throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Desktop output, raw output, and result file must be distinct files directly inside the approved handoff directory");
  }
  if (targets.some((target) => fs.existsSync(target))) {
    throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Desktop output target already exists; refusing a possibly duplicate submission");
  }
  return { output, rawOutput, resultFile };
}

async function withRuntime(options, runtimeFactory, callback) {
  const runtime = await runtimeFactory({ endpoint: options.endpoint, targetUrl: options.targetUrl, timeoutMs: options.timeoutMs, signal: options.signal });
  try { return await callback(runtime); }
  finally { runtime.close(); }
}

async function runProbe(options, runtimeFactory = connectDesktopRuntime) {
  return withRuntime(options, runtimeFactory, async (runtime) => ({
    ok: true,
    channel: "desktop-cdp",
    endpoint: runtime.endpoint,
    target_url: runtime.targetUrl,
    desktop_bridge: runtime.capabilities.desktop_bridge === true,
    desktop_environment_readable: runtime.capabilities.desktop_environment_readable === true,
    device_check_supported: runtime.capabilities.device_check_supported === true,
    chunked_message_supported: runtime.capabilities.chunked_message_supported === true,
    app_version: runtime.capabilities.app_version || null,
  }));
}

async function runModels(options, runtimeFactory = connectDesktopRuntime) {
  return withRuntime(options, runtimeFactory, async (runtime) => runtime.conversation.getAvailableModels());
}

async function runAsk(options, runtimeFactory = connectDesktopRuntime) {
  if (!options.model) throw new DesktopRuntimeError("MODEL_NOT_FOUND", "ask requires --model");
  if (!options.output) throw new DesktopRuntimeError("CONVERSATION_REJECTED", "ask requires --output");
  const authorization = loadAuthorization(options);
  if (path.resolve(options.promptFile || "") !== path.resolve(authorization.message_path || "")) {
    throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Prompt file is not the approved outbound message artifact");
  }
  if (authorization.target_url !== DEFAULT_TARGET_URL || options.targetUrl && options.targetUrl !== authorization.target_url) {
    throw new DesktopRuntimeError("TARGET_NOT_FOUND", "Desktop authorization target does not match the exact phase-1 renderer");
  }
  if (options.model !== authorization.model_id || (options.thinkingEffort || null) !== authorization.thinking_effort) {
    throw new DesktopRuntimeError("MODEL_NOT_FOUND", "Requested Desktop model or thinking effort is not the approved live-catalog resolution");
  }
  const targets = outputTargets(options, options.handoffDir || path.dirname(authorization.message_path));
  const prompt = readPrompt(options.promptFile);
  const promptHash = sha256(Buffer.from(prompt, "utf8"));
  assertHash(options.expectedPromptSha256, "--prompt-sha256");
  assertHash(options.manifestSha256, "--manifest-sha256");
  if (authorization.message_sha256 !== promptHash ||
      (options.expectedPromptSha256 && options.expectedPromptSha256 !== promptHash)) {
    throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Prompt hash does not match the approved value");
  }
  if (options.manifestSha256 && options.manifestSha256 !== authorization.manifest_sha256) {
    throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Manifest hash does not match the approved value");
  }
  const packageId = packageIdFrom(prompt, options.packageId || authorization.package_id);
  if (packageId !== authorization.package_id) {
    throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Package id does not match the approved value");
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DesktopRuntimeError("TIMEOUT", "Desktop ask timed out")), options.timeoutMs);
  const cancel = () => controller.abort(new DesktopRuntimeError("CANCELLED", "Desktop ask was cancelled"));
  process.once("SIGINT", cancel);
  let response;
  try {
    response = await withRuntime({ ...options, signal: controller.signal }, runtimeFactory, (runtime) => runtime.conversation.startChat({
      prompt,
      model: options.model,
      thinkingEffort: options.thinkingEffort || null,
      signal: controller.signal,
      continuation: null,
    }));
  } finally { clearTimeout(timer); process.removeListener("SIGINT", cancel); }
  const begin = `BEGIN_GPTPRO_RESPONSE:${packageId}`;
  const end = `END_GPTPRO_RESPONSE:${packageId}`;
  if (response.complete !== true) {
    throw new DesktopRuntimeError("STREAM_INTERRUPTED", "Desktop conversation did not emit a proven completion event");
  }
  const raw = response.text;
  if (raw.includes(begin) || raw.includes(end)) {
    throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Captured assistant text already contains package response markers");
  }
  if (response.local_function_signatures_count !== 0 || response.tools_enabled !== false) {
    throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Phase-1 Desktop ask did not prove local tools were disabled");
  }
  const wrapped = `${begin}\n${raw}${raw.endsWith("\n") ? "" : "\n"}${end}\n`;
  const { output, rawOutput, resultFile } = targets;
  const rawHash = sha256(Buffer.from(raw, "utf8"));
  const wrappedHash = sha256(Buffer.from(wrapped, "utf8"));
  const result = {
    ok: true,
    completed: true,
    channel: "desktop-cdp",
    package_id: packageId,
    manifest_sha256: authorization.manifest_sha256,
    prompt_sha256: promptHash,
    model_id: response.model_id,
    requested_thinking_effort: response.requested_thinking_effort,
    observed_thinking_effort: response.observed_thinking_effort,
    conversation_id: response.conversation_id || null,
    message_id: response.message_id || null,
    parent_message_id: response.parent_message_id || null,
    local_function_signatures_count: 0,
    tools_enabled: false,
    server_tool_event_count: Array.isArray(response.server_tool_events) ? response.server_tool_events.length : 0,
    sources: Array.isArray(response.sources) ? response.sources : [],
    marker_origin: "runtime",
    raw_response_sha256: rawHash,
    wrapped_response_sha256: wrappedHash,
    raw_output: rawOutput,
    output,
    completed_at: new Date().toISOString(),
  };
  atomicWrite(rawOutput, raw, { exclusive: true });
  atomicWrite(output, wrapped, { exclusive: true });
  atomicWrite(resultFile, `${JSON.stringify(result, null, 2)}\n`, { exclusive: true });
  return { ...result, result_file: resultFile };
}

async function main(argv = process.argv.slice(2), { runtimeFactory = connectDesktopRuntime, stdout = process.stdout, stderr = process.stderr } = {}) {
  try {
    const options = parseArgs(argv);
    if (options.help) { stdout.write(`${usage()}\n`); return 0; }
    const result = options.command === "probe" ? await runProbe(options, runtimeFactory) :
      options.command === "models" ? await runModels(options, runtimeFactory) :
        await runAsk(options, runtimeFactory);
    stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return 0;
  } catch (error) {
    stderr.write(`${JSON.stringify(errorPayload(asRuntimeError(error)), null, 2)}\n`);
    return 1;
  }
}

if (require.main === module) main().then((code) => { process.exitCode = code; });

module.exports = { usage, parseArgs, sha256, atomicWrite, outputTargets, readPrompt, packageIdFrom, loadAuthorization, runProbe, runModels, runAsk, main };
