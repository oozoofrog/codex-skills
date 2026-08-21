"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { DEFAULT_TARGET_URL, validateEndpoint, validateWebSocketUrl, selectExactTarget, discoverTarget } = require("../runtime/chatgpt-desktop/cdp-client");
const vm = require("node:vm");
const { MARKER, ChunkedMessageAssembler, isChunkFrame, rendererRelaySource } = require("../runtime/chatgpt-desktop/chunked-message");
const { BASE_REQUEST_HEADERS, DEVICE_CHECK_HEADERS, DesktopBridge } = require("../runtime/chatgpt-desktop/desktop-bridge");
const { ChatGptDesktopConversationClient } = require("../runtime/chatgpt-desktop/conversation-client");
const { DeltaDecoder, applyOperation, expandOperation } = require("../runtime/chatgpt-desktop/delta-decoder");
const { assertRendererIdentity } = require("../runtime/chatgpt-desktop");
const { DesktopRuntimeError } = require("../runtime/chatgpt-desktop/errors");
const { normalizeDesktopCatalog, resolveDesktopModel, resolveThinkingEffort } = require("../runtime/chatgpt-desktop/model-catalog");
const { loadAuthorization, runAsk, runModels, runProbe, sha256 } = require("../scripts/chatgpt-desktop");

function runtimeErrorCode(error) { return error?.code; }

test("CDP endpoint validation permits loopback only", () => {
  for (const endpoint of ["http://127.0.0.1:9222", "http://localhost:9222", "http://[::1]:9222"]) {
    assert.doesNotThrow(() => validateEndpoint(endpoint));
  }
  for (const endpoint of ["http://example.com:9222", "http://user:pass@127.0.0.1:9222", "file:///tmp/cdp", "ws://127.0.0.1:9222", "http://127.0.0.1:9222/not-root"]) {
    assert.throws(() => validateEndpoint(endpoint), (error) => runtimeErrorCode(error) === "CDP_ENDPOINT_REJECTED");
  }
  assert.doesNotThrow(() => validateWebSocketUrl("ws://127.0.0.1:9222/devtools/page/1"));
  assert.throws(() => validateWebSocketUrl("ws://192.168.1.10:9222/devtools/page/1"), /loopback/);
});

test("CDP discovery reports a stable connection failure", async () => {
  await assert.rejects(
    () => discoverTarget({ endpoint: "http://127.0.0.1:9222", fetchImpl: async () => { throw new Error("secret-cookie-value"); } }),
    (error) => error.code === "CDP_UNAVAILABLE" && !error.message.includes("secret-cookie-value"),
  );
});

test("target discovery selects exactly the ChatGPT renderer", () => {
  const intended = { type: "page", url: "app://-/index.html", webSocketDebuggerUrl: "ws://127.0.0.1:9222/devtools/page/2" };
  const target = selectExactTarget([
    { type: "page", url: "https://example.com", webSocketDebuggerUrl: "ws://127.0.0.1:9222/devtools/page/1" },
    intended,
  ]);
  assert.equal(target, intended);
  assert.throws(() => selectExactTarget([{ type: "page", url: "https://example.com" }]), (error) => error.code === "TARGET_NOT_FOUND");
  assert.throws(() => selectExactTarget([intended, { ...intended }]), (error) => error.code === "TARGET_NOT_FOUND");
  assert.doesNotThrow(() => assertRendererIdentity(DEFAULT_TARGET_URL));
  assert.throws(() => assertRendererIdentity("https://chatgpt.com/"), (error) => error.code === "TARGET_NOT_FOUND");
});

test("probe returns only normalized capability fields", async () => {
  const runtimeFactory = async () => ({
    endpoint: "http://127.0.0.1:9222", targetUrl: "app://-/index.html",
    capabilities: { desktop_bridge: true, desktop_environment_readable: true, device_check_supported: true, chunked_message_supported: true, app_version: "26.818.21641", token: "must-not-leak" },
    close() {},
  });
  const result = await runProbe({ endpoint: "http://127.0.0.1:9222", targetUrl: "app://-/index.html", timeoutMs: 100 }, runtimeFactory);
  assert.equal(result.ok, true);
  assert.equal(result.desktop_bridge, true);
  assert.equal(result.device_check_supported, true);
  assert.equal(result.chunked_message_supported, true);
  assert.equal(JSON.stringify(result).includes("must-not-leak"), false);
});

test("probe fails closed for missing bridge and DeviceCheck", async () => {
  class FakeCdp {
    constructor(capabilities) { this.capabilityValue = capabilities; this.listener = null; }
    async send() {}
    onEvent(listener) { this.listener = listener; return () => {}; }
    async evaluate(expression) { return expression.includes("desktop_bridge") ? this.capabilityValue : true; }
  }
  const missing = new DesktopBridge(new FakeCdp({ desktop_bridge: false, device_check_supported: false }));
  await assert.rejects(() => missing.capabilities(), (error) => error.code === "BRIDGE_UNAVAILABLE");
  const noDeviceCheck = new DesktopBridge(new FakeCdp({ desktop_bridge: true, device_check_supported: false }));
  await assert.rejects(() => noDeviceCheck.capabilities(), (error) => error.code === "DEVICE_CHECK_UNAVAILABLE");
});

test("Desktop bridge attaches DeviceCheck only when explicitly requested", async () => {
  const sent = [];
  const bridge = new DesktopBridge(null, { timeoutMs: 100 });
  bridge._send = async (message) => {
    sent.push(message);
    queueMicrotask(() => bridge._route({
      type: "fetch-response", responseType: "success", requestId: message.requestId,
      status: 200, bodyJsonString: "{}",
    }));
  };
  await bridge.request({ method: "GET", url: "/models" });
  await bridge.request({ method: "GET", url: "/ios/attestation_challenge", headers: DEVICE_CHECK_HEADERS });
  assert.deepEqual(sent[0].headers, BASE_REQUEST_HEADERS);
  assert.equal(sent[0].headers["OAI-Language"], "en");
  assert.equal(sent[0].headers["X-OpenAI-Attach-DeviceCheck-Token"], undefined);
  assert.equal(sent[1].headers["X-OpenAI-Attach-DeviceCheck-Token"], "1");
  assert.equal(sent[1].headers["X-OpenAI-Attach-Auth"], "1");
});

test("Desktop bridge preserves timeout reasons and classifies ambiguous stream failure", async () => {
  const bridge = new DesktopBridge(null, { timeoutMs: 1000 });
  bridge._send = async () => {};
  const controller = new AbortController();
  const request = bridge.request({ url: "/models", signal: controller.signal });
  controller.abort(new DesktopRuntimeError("TIMEOUT", "outer timeout"));
  await assert.rejects(() => request, (error) => error.code === "TIMEOUT");

  const stream = await bridge.stream({ url: "/f/conversation", body: "{}" });
  const requestId = [...bridge.pending.keys()][0];
  bridge._route({ type: "fetch-stream-error", requestId, error: "must-not-leak" });
  await assert.rejects(async () => {
    for await (const ignored of stream) void ignored;
  }, (error) => error.code === "STREAM_INTERRUPTED" && !error.message.includes("must-not-leak"));
});

test("Desktop bridge rechecks the exact renderer immediately before a sensitive send", async () => {
  const bridge = new DesktopBridge({
    async evaluate() { return { ok: false, target_mismatch: true }; },
  }, { timeoutMs: 100 });
  await assert.rejects(
    () => bridge.request({ url: "/models" }),
    (error) => error.code === "TARGET_NOT_FOUND",
  );
});

test("chunked Desktop messages require consecutive frames and acknowledge each frame", async () => {
  const acknowledgements = [];
  const assembler = new ChunkedMessageAssembler({ acknowledge: async (...value) => acknowledgements.push(value) });
  assert.deepEqual(await assembler.accept({ marker: MARKER, transferId: "one", sequence: 0, kind: "start" }), { complete: false });
  assert.deepEqual(await assembler.accept({
    marker: MARKER, transferId: "one", sequence: 1, kind: "chunk",
    tokens: [{ type: "object-start" }, { type: "key", value: "type" }, { type: "value", value: "fetch-response" }, { type: "key", value: "requestId" }, { type: "value", value: "request-1" }, { type: "container-end" }],
  }), { complete: false });
  const completed = await assembler.accept({ marker: MARKER, transferId: "one", sequence: 2, kind: "end" });
  assert.deepEqual(completed.value, { type: "fetch-response", requestId: "request-1" });
  assert.deepEqual(acknowledgements, [["one", 0], ["one", 1], ["one", 2]]);
  await assert.rejects(
    () => assembler.accept({ marker: MARKER, transferId: "gap", sequence: 2, kind: "chunk", tokens: [] }),
    (error) => error.code === "STREAM_PROTOCOL_ERROR",
  );
  assert.equal(isChunkFrame({ protocol: MARKER }), false);
});

test("renderer relay keeps raw chunks inside the renderer and forwards only active completed responses", () => {
  const listeners = {};
  const forwarded = [];
  const fakeWindow = {
    addEventListener(name, listener) { listeners[name] = listener; },
    __binding(payload) { forwarded.push(JSON.parse(payload)); },
  };
  vm.runInNewContext(rendererRelaySource("__binding", ["fetch-response"]), { window: fakeWindow, JSON, Object, Set, Symbol, Number, Array, Error });
  fakeWindow.__gptproDesktopRequestIds.add("active");
  const frames = (requestId, transferId) => [
    { marker: MARKER, transferId, sequence: 0, kind: "start" },
    { marker: MARKER, transferId, sequence: 1, kind: "chunk", tokens: [
      { type: "object-start" }, { type: "key", value: "type" }, { type: "value", value: "fetch-response" },
      { type: "key", value: "requestId" }, { type: "value", value: requestId }, { type: "container-end" },
    ] },
    { marker: MARKER, transferId, sequence: 2, kind: "end" },
  ];
  for (const data of frames("unrelated", "one")) listeners.message({ data });
  assert.deepEqual(forwarded, []);
  for (const data of frames("active", "two")) listeners.message({ data });
  assert.deepEqual(forwarded, [{ type: "fetch-response", requestId: "active" }]);
});

test("dynamic model catalog normalization never claims fallback entitlement", () => {
  const catalog = normalizeDesktopCatalog({
    models: [
      { slug: "gpt-live", title: "GPT Live", default_thinking_effort: "standard" },
      { slug: "backend-hidden", title: "Hidden backend" },
      { slug: "admin-disabled", title: "Disabled" },
    ],
    categories: [{ default_model: "admin-disabled", disabled_by_admin: true }],
    slider_settings: [{ model_slug: "gpt-live", thinking_effort: "extended" }],
    versions: [
      { disabled: true, intelligence_presets: [{ model_slug: "backend-hidden" }] },
      { intelligence_presets: [{ model_slug: "gpt-live", thinking_effort: "xhigh" }] },
    ],
  });
  assert.equal(catalog.source, "dynamic");
  assert.equal(catalog.catalog_scope, "selectable-public-options-and-versions");
  assert.deepEqual(catalog.models.map((model) => model.id), ["gpt-live"]);
  assert.deepEqual(catalog.models[0].thinking_efforts, ["standard", "extended", "xhigh"]);
  assert.equal(resolveDesktopModel(catalog.models, "gpt-live").name, "GPT Live");
  assert.equal(resolveThinkingEffort(catalog.models[0], "extended"), "extended");
  assert.throws(() => resolveThinkingEffort(catalog.models[0], "ultra"), (error) => error.code === "MODEL_EFFORT_UNSUPPORTED");
  assert.throws(() => resolveDesktopModel(catalog.models, "not-entitled"), (error) => error.code === "MODEL_NOT_FOUND");
  assert.throws(
    () => resolveDesktopModel([{ ...catalog.models[0], id: "one", name: "Same" }, { ...catalog.models[0], id: "two", name: "Same" }], "same"),
    (error) => error.code === "MODEL_AMBIGUOUS",
  );
  assert.throws(() => normalizeDesktopCatalog({ error: "server unavailable" }), (error) => error.code === "MODEL_CATALOG_FAILED");
});

test("dynamic model catalog includes public version options and reports workspace policy", () => {
  const payload = {
    models: [{ slug: "standard", title: "Standard" }, { slug: "pro", title: "Pro" }],
    versions: [
      { id: "v1", intelligence_presets: [{ model_slug: "standard" }] },
      { id: "v2", intelligence_presets: [{ model_slug: "pro", thinking_effort: "extended" }] },
    ],
    workspace_model_policy: {
      selection: { model: "pro", thinking_effort: "extended" },
      new_thread_precedence: "prefer_policy",
    },
  };
  const catalog = normalizeDesktopCatalog(payload);
  assert.deepEqual(catalog.models.map((model) => model.id), ["standard", "pro"]);
  assert.equal(catalog.workspace_policy.preferred_for_new_thread, true);
  assert.equal(catalog.workspace_policy.thinking_effort, "extended");
  const invalid = structuredClone(payload);
  invalid.workspace_model_policy.selection.model = "internal-only";
  const fallback = normalizeDesktopCatalog(invalid);
  assert.equal(fallback.workspace_policy.model_id, null);
  assert.equal(fallback.workspace_policy.resolved, false);
});

test("models returns the live runtime-owned schema", async () => {
  const expected = { source: "dynamic", models: [{ id: "gpt-live", name: "GPT Live", reasoning: false, thinking_efforts: [], context_window: 0 }] };
  let closed = false;
  const result = await runModels({ timeoutMs: 100 }, async () => ({
    conversation: { async getAvailableModels() { return expected; } },
    close() { closed = true; },
  }));
  assert.deepEqual(result, expected);
  assert.equal(closed, true);
});

test("ask authorization is obtained from the read-only Python governance command", () => {
  let invocation = null;
  const expected = {
    authorized: true, phase: "approved", delivery_channel: "desktop-cdp", tools_enabled: false,
    package_id: "package", manifest_sha256: "a".repeat(64), message_path: "/tmp/message.md",
    message_sha256: "b".repeat(64), target_url: DEFAULT_TARGET_URL,
    model_id: "backend-pro", thinking_effort: "extended",
  };
  const authorization = loadAuthorization({ handoffDir: "/tmp/handoff" }, (command, args, options) => {
    invocation = { command, args, options };
    return { status: 0, stdout: JSON.stringify(expected), stderr: "" };
  });
  assert.deepEqual(authorization, expected);
  assert.equal(invocation.command, "python3");
  assert.deepEqual(invocation.args.slice(-3), ["desktop-authorization", "--handoff-dir", "/tmp/handoff"]);
  assert.throws(
    () => loadAuthorization({ handoffDir: "/tmp/handoff" }, () => ({ status: 2, stdout: "", stderr: "secret-value" })),
    (error) => error.code === "CONVERSATION_REJECTED" && !error.message.includes("secret-value"),
  );
});

test("conversation request selects exact model and disables tool signatures", async () => {
  let submittedBody = null;
  const requests = [];
  const bridge = {
    async request(request) {
      requests.push(request);
      if (request.url.startsWith("/models")) return { status: 200, body: {
        models: [{ slug: "backend-pro", title: "Pro", default_thinking_effort: "extended" }],
        versions: [{ intelligence_presets: [{ model_slug: "backend-pro", thinking_effort: "extended" }] }],
      } };
      return { status: 200, body: { attestation_challenge: "ephemeral-challenge" } };
    },
    async stream(request) {
      submittedBody = JSON.parse(request.body);
      assert.equal(request.headers, undefined);
      return (async function* () {
        yield { event: "message", data: JSON.stringify({ conversation_id: "conv-1", message: { id: "msg-1", author: { role: "assistant" }, content: { content_type: "text", parts: ["Complete answer"] } } }) };
        yield { event: "message_stream_complete", data: JSON.stringify({ conversation_id: "conv-1" }) };
      }());
    },
  };
  const client = new ChatGptDesktopConversationClient(bridge);
  const result = await client.startChat({ prompt: "Approved prompt", model: "backend-pro", thinkingEffort: "extended" });
  assert.equal(submittedBody.model, "backend-pro");
  assert.equal(submittedBody.thinking_effort, "extended");
  assert.deepEqual(submittedBody.supported_encodings, ["v1"]);
  assert.deepEqual(submittedBody.local_function_signatures, []);
  assert.equal(submittedBody.app_attest_challenge, "ephemeral-challenge");
  assert.equal(submittedBody.conversation_id, undefined);
  assert.equal(requests[0].headers, undefined);
  assert.deepEqual(requests[1].headers, DEVICE_CHECK_HEADERS);
  assert.equal(result.text, "Complete answer");
  assert.equal(result.conversation_id, "conv-1");
  assert.equal(result.message_id, "msg-1");
  assert.equal(result.tools_enabled, false);
});

test("delta decoder assembles v1 append operations and sources", () => {
  const decoder = new DeltaDecoder();
  decoder.consume({ event: "delta_encoding", data: "v1" });
  decoder.consume({ event: "delta", data: JSON.stringify({ c: "final", o: "add", p: [], v: "Hello" }) });
  decoder.consume({ event: "delta", data: JSON.stringify({ o: "append", v: " world" }) });
  decoder.consume({ event: "message_stream_complete", data: JSON.stringify({ conversation_id: "conv-delta", sources: [{ title: "Reference", url: "https://example.com/source" }] }) });
  const result = decoder.result();
  assert.equal(result.text, "Hello world");
  assert.equal(result.sources[0].url, "https://example.com/source");
  assert.equal(result.conversation_id, "conv-delta");
  assert.equal(result.complete, true);
});

test("delta decoder follows numeric paths, relative patches, append types, and no value inheritance", () => {
  const previous = expandOperation({ c: "final", p: "/items/0", o: "add", v: "first" });
  assert.deepEqual(expandOperation({ o: "append" }, previous), {
    channel: "final", path: "/items/0", op: "append", value: undefined,
  });
  let value = applyOperation(undefined, { op: "add", path: "/items/0", value: "first" });
  value = applyOperation(value, { op: "add", path: "/items/1", value: "second" });
  value = applyOperation(value, { op: "patch", path: "/items", value: [{ o: "append", p: "/0", v: "!" }] });
  value = applyOperation(value, { op: "append", path: "/metadata", value: { reviewed: true } });
  assert.deepEqual(value, { items: ["first!", "second"], metadata: { reviewed: true } });
  assert.equal(expandOperation({ v: null }, previous).value, null);
  assert.deepEqual(
    applyOperation({}, { op: "patch", path: "/missing/nested", value: [{ o: "add", p: "", v: { created: true } }] }),
    { missing: { nested: { created: true } } },
  );
});

test("delta decoder parses full per-channel message values and accepts recipient all", () => {
  const decoder = new DeltaDecoder();
  decoder.consume({ event: "delta_encoding", data: "v1" });
  decoder.consume({ event: "delta", data: JSON.stringify({
    c: "final", p: "", o: "add", v: {
      conversation_id: "conv-root",
      message: { id: "msg-root", author: { role: "assistant" }, recipient: "all", content: { content_type: "text", parts: ["Broadcast answer"] } },
    },
  }) });
  decoder.consume({ event: "message_stream_complete", data: JSON.stringify({ conversation_id: "conv-root" }) });
  const result = decoder.result();
  assert.equal(result.text, "Broadcast answer");
  assert.equal(result.message_id, "msg-root");
  assert.equal(result.server_tool_events.length, 0);
});

test("delta decoder rejects transport EOF without message completion", () => {
  const decoder = new DeltaDecoder();
  decoder.consume({ event: "message", data: JSON.stringify({ message: { id: "partial", author: { role: "assistant" }, content: { parts: ["partial"] } } }) });
  assert.throws(() => decoder.result(), (error) => error.code === "STREAM_INTERRUPTED");
});

test("delta decoder records server tool events without exposing a local tool relay", () => {
  const decoder = new DeltaDecoder();
  decoder.consume({ event: "message", data: JSON.stringify({ message: { id: "tool", author: { role: "assistant" }, recipient: "server.search", content: { content_type: "tool_call", parts: [] } } }) });
  decoder.consume({ event: "message", data: JSON.stringify({ message: { id: "answer", author: { role: "assistant" }, content: { content_type: "text", parts: ["Answer after server-side work"] } } }) });
  decoder.consume({ event: "message_stream_complete", data: JSON.stringify({ conversation_id: "conv" }) });
  const result = decoder.result();
  assert.equal(result.server_tool_events.length, 1);
  assert.equal(result.server_tool_events[0].recipient, "server.search");
  assert.match(result.text, /Answer after server-side work/);
});

function fakeAskRuntime(responseOverrides = {}, capture = {}) {
  return async () => ({
    conversation: {
      async startChat(request) {
        capture.request = request;
        return {
          text: "Advisory answer with citation https://example.com\n",
          model_id: "backend-pro",
          requested_thinking_effort: request.thinkingEffort,
          observed_thinking_effort: request.thinkingEffort || "extended",
          conversation_id: "conversation-1",
          message_id: "message-1",
          parent_message_id: "message-1",
          tools_enabled: false,
          local_function_signatures_count: 0,
          complete: true,
          ...responseOverrides,
        };
      },
    },
    close() { capture.closed = true; },
  });
}

function askFixture() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gptpro-desktop-test-"));
  const packageId = "20260821T000000Z-review-deadbeef";
  const prompt = `# Prompt\n\nPackage: \`${packageId}\`\n\nReturn advice without markers.\n`;
  const promptFile = path.join(directory, "prompt.md");
  fs.writeFileSync(promptFile, prompt);
  const manifestSha256 = "a".repeat(64);
  return {
    directory, packageId, prompt, promptFile, manifestSha256,
    output: path.join(directory, "desktop-response.md"),
    authorization: {
      authorized: true,
      phase: "approved",
      delivery_channel: "desktop-cdp",
      tools_enabled: false,
      package_id: packageId,
      manifest_sha256: manifestSha256,
      message_path: promptFile,
      message_sha256: sha256(Buffer.from(prompt)),
      target_url: DEFAULT_TARGET_URL,
      model_id: "backend-pro",
      thinking_effort: "extended",
    },
  };
}

function authorizedAskOptions(fixture, overrides = {}) {
  return {
    authorization: { ...fixture.authorization, thinking_effort: overrides.thinkingEffort || null },
    targetUrl: DEFAULT_TARGET_URL,
    ...overrides,
  };
}

test("ask rejects a model or effort that differs from the approved live resolution before CDP", async () => {
  const fixture = askFixture();
  let connected = false;
  await assert.rejects(() => runAsk({
    ...authorizedAskOptions(fixture, {
      promptFile: fixture.promptFile, model: "backend-pro", output: fixture.output,
      packageId: fixture.packageId, timeoutMs: 100,
    }),
    authorization: { ...fixture.authorization, model_id: "another-model", thinking_effort: null },
  }, async () => { connected = true; throw new Error("must not connect"); }), (error) => error.code === "MODEL_NOT_FOUND");
  assert.equal(connected, false);
});

test("ask reads a file, wraps one complete turn atomically, and records both hashes", async () => {
  const fixture = askFixture();
  const manifestHash = fixture.manifestSha256;
  const capture = {};
  const result = await runAsk(authorizedAskOptions(fixture, {
    promptFile: fixture.promptFile, model: "backend-pro", thinkingEffort: "extended",
    output: fixture.output, packageId: fixture.packageId, manifestSha256: manifestHash,
    expectedPromptSha256: sha256(Buffer.from(fixture.prompt)), timeoutMs: 500,
  }), fakeAskRuntime({}, capture));
  const raw = fs.readFileSync(result.raw_output, "utf8");
  const wrapped = fs.readFileSync(result.output, "utf8");
  assert.equal(capture.request.prompt, fixture.prompt);
  assert.equal(capture.request.model, "backend-pro");
  assert.equal(capture.request.continuation, null);
  assert.equal(capture.closed, true);
  assert.equal(wrapped.match(new RegExp(`BEGIN_GPTPRO_RESPONSE:${fixture.packageId}`, "g")).length, 1);
  assert.equal(wrapped.match(new RegExp(`END_GPTPRO_RESPONSE:${fixture.packageId}`, "g")).length, 1);
  assert.equal(result.raw_response_sha256, sha256(Buffer.from(raw)));
  assert.equal(result.wrapped_response_sha256, sha256(Buffer.from(wrapped)));
  assert.notEqual(result.raw_response_sha256, result.wrapped_response_sha256);
  assert.equal(result.marker_origin, "runtime");
  assert.equal(result.local_function_signatures_count, 0);
  assert.equal(result.conversation_id, "conversation-1");
  assert.equal(JSON.parse(fs.readFileSync(result.result_file, "utf8")).wrapped_response_sha256, result.wrapped_response_sha256);
});

test("ask rejects missing, empty, mismatched, and pre-marked prompt/response data", async () => {
  const fixture = askFixture();
  await assert.rejects(() => runAsk(authorizedAskOptions(fixture, { model: "backend-pro", output: fixture.output, timeoutMs: 100 }), fakeAskRuntime()), (error) => error.code === "CONVERSATION_REJECTED");
  fs.writeFileSync(fixture.promptFile, "\n");
  await assert.rejects(() => runAsk(authorizedAskOptions(fixture, { promptFile: fixture.promptFile, model: "backend-pro", output: fixture.output, packageId: fixture.packageId, timeoutMs: 100 }), fakeAskRuntime()), (error) => error.code === "CONVERSATION_REJECTED");
  fs.writeFileSync(fixture.promptFile, fixture.prompt);
  await assert.rejects(() => runAsk(authorizedAskOptions(fixture, { promptFile: fixture.promptFile, model: "backend-pro", output: fixture.output, packageId: fixture.packageId, expectedPromptSha256: "b".repeat(64), timeoutMs: 100 }), fakeAskRuntime()), /Prompt hash/);
  await assert.rejects(() => runAsk(authorizedAskOptions(fixture, { promptFile: fixture.promptFile, model: "backend-pro", output: fixture.output, packageId: fixture.packageId, timeoutMs: 100 }), fakeAskRuntime({ text: `BEGIN_GPTPRO_RESPONSE:${fixture.packageId}\nbody\n` })), (error) => error.code === "STREAM_PROTOCOL_ERROR");
});

test("ask cancellation or failure does not replace an existing response artifact", async () => {
  const fixture = askFixture();
  fs.writeFileSync(fixture.output, "old-response\n");
  const runtimeFactory = async () => ({
    conversation: {
      startChat({ signal }) {
        return new Promise((resolve, reject) => {
          signal.addEventListener("abort", () => reject(signal.reason), { once: true });
        });
      },
    },
    close() {},
  });
  await assert.rejects(() => runAsk(authorizedAskOptions(fixture, {
    promptFile: fixture.promptFile, model: "backend-pro", output: fixture.output,
    packageId: fixture.packageId, timeoutMs: 20,
  }), runtimeFactory), (error) => error.code === "CONVERSATION_REJECTED");
  assert.equal(fs.readFileSync(fixture.output, "utf8"), "old-response\n");

  fs.unlinkSync(fixture.output);
  await assert.rejects(() => runAsk(authorizedAskOptions(fixture, {
    promptFile: fixture.promptFile, model: "backend-pro", output: fixture.output,
    packageId: fixture.packageId, timeoutMs: 20,
  }), runtimeFactory), (error) => error.code === "TIMEOUT");
  assert.equal(fs.existsSync(fixture.output), false);
});

test("ask timeout also cancels the pre-conversation CDP connection stage", async () => {
  const fixture = askFixture();
  let observedSignal = null;
  const runtimeFactory = ({ signal }) => {
    observedSignal = signal;
    return new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
  };
  await assert.rejects(() => runAsk(authorizedAskOptions(fixture, {
    promptFile: fixture.promptFile, model: "backend-pro", thinkingEffort: "extended",
    output: fixture.output, packageId: fixture.packageId, timeoutMs: 20,
  }), runtimeFactory), (error) => error.code === "TIMEOUT");
  assert.equal(observedSignal.aborted, true);
  assert.equal(fs.existsSync(fixture.output), false);
});

test("stream interruption after visible output is not retried", async () => {
  let streamCalls = 0;
  const bridge = {
    async request(request) {
      if (request.url.startsWith("/models")) return { status: 200, body: {
        models: [{ slug: "backend-pro", title: "Pro" }],
        versions: [{ intelligence_presets: [{ model_slug: "backend-pro" }] }],
      } };
      return { status: 200, body: { attestation_challenge: "challenge" } };
    },
    async stream() {
      streamCalls += 1;
      return (async function* () {
        yield { event: "message", data: JSON.stringify({ message: { id: "msg", author: { role: "assistant" }, content: { parts: ["partial"] } } }) };
        const error = new Error("connection lost"); error.code = "STREAM_INTERRUPTED"; throw error;
      }());
    },
  };
  await assert.rejects(() => new ChatGptDesktopConversationClient(bridge).startChat({ prompt: "prompt", model: "backend-pro" }));
  assert.equal(streamCalls, 1);
});
