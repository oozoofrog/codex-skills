"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  CdpClient,
  DEFAULT_ENDPOINT,
  RUNNER_PORT,
  RUNNER_PROFILE,
  assertDebuggerUrl,
  listenerCommandError,
  listenerInspectionError,
  parseListenerOutput,
  parseProcessTable,
  selectRendererTarget,
  validateEndpoint,
  verifyListenerGroupIdentity,
  verifyListenerIdentity,
} = require("../runtime/chatgpt-desktop/cdp-client.js");
const { installAppHostHttpRuntime } = require("../runtime/chatgpt-desktop/app-host-http.js");
const { PrivateDesktopBridge } = require("../runtime/chatgpt-desktop/private-bridge.js");
const { normalizeCatalog, resolveModel } = require("../runtime/chatgpt-desktop/model-catalog.js");
const { ConversationDecoder, DeltaState, parseSse } = require("../runtime/chatgpt-desktop/delta-decoder.js");
const { PrivateConversationClient, conversationPayload } = require("../runtime/chatgpt-desktop/conversation-client.js");
const { responseFromConversation, waitForConversationResponse } = require("../runtime/chatgpt-desktop/conversation-readback.js");
const { handoffTopic, StreamHandoff, topicHash } = require("../runtime/chatgpt-desktop/stream-handoff.js");
const { sanitizedError } = require("../runtime/chatgpt-desktop/errors.js");
const { main: desktopMain } = require("../scripts/chatgpt-desktop.js");

function conversationDetail(messageId, prompt, text = "완료", overrides = {}) {
  const final = {
    id: "assistant-message",
    author: { role: "assistant" },
    recipient: "all",
    channel: "final",
    status: "finished_successfully",
    end_turn: true,
    content: { content_type: "text", parts: [text] },
    ...overrides,
  };
  return {
    id: "conversation",
    current_node: "assistant-node",
    mapping: {
      "user-node": {
        id: "user-node",
        parent: null,
        children: ["assistant-node"],
        message: {
          id: messageId,
          author: { role: "user" },
          recipient: "all",
          content: { content_type: "text", parts: [prompt] },
        },
      },
      "assistant-node": {
        id: "assistant-node",
        parent: "user-node",
        children: [],
        message: final,
      },
    },
  };
}

function readbackRequest(messageId, prompt, text = "완료") {
  return async (method, url) => {
    if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
    if (url.startsWith("/conversations?")) {
      return { status: 200, body: { items: [{ id: "conversation", update_time: new Date().toISOString() }] } };
    }
    if (url === "/conversation/conversation") return { status: 200, body: conversationDetail(messageId, prompt, text) };
    throw new Error(`unexpected request ${method} ${url}`);
  };
}

test("CDP endpoint accepts only credential-free loopback HTTP", () => {
  assert.equal(DEFAULT_ENDPOINT, "http://127.0.0.1:9223");
  assert.equal(RUNNER_PORT, 9223);
  for (const value of ["http://127.0.0.1:9222", "http://localhost:9222", "http://[::1]:9222"]) {
    assert.equal(validateEndpoint(value).port, "9222");
  }
  for (const value of [
    "http://example.com:9222",
    "https://127.0.0.1:9222",
    "http://user:pass@127.0.0.1:9222",
    "file:///tmp/socket",
    "http://127.0.0.1:9222/json",
  ]) assert.throws(() => validateEndpoint(value), { code: "CDP_ENDPOINT_REJECTED" });
});

test("missing listener is availability failure, not unverifiable ownership", () => {
  assert.throws(
    () => { throw listenerInspectionError({ code: 1, stdout: "" }); },
    { code: "CDP_UNAVAILABLE", retryable: true },
  );
  assert.throws(
    () => { throw listenerInspectionError({ code: "EACCES", stdout: "" }); },
    { code: "CDP_LISTENER_UNVERIFIED" },
  );
});

test("listener command failure is retryable only before submission", () => {
  const error = listenerCommandError(new Error("transient process-table failure"));
  assert.equal(error.code, "CDP_LISTENER_UNVERIFIED");
  assert.equal(error.retryable, true);
  assert.equal(error.submissionState, "not_started");
});

test("target discovery accepts exactly one ChatGPT renderer", () => {
  const target = { type: "page", url: "app://-/index.html", webSocketDebuggerUrl: "ws://127.0.0.1:9222/devtools/page/1" };
  assert.equal(selectRendererTarget([{ type: "page", url: "https://example.com", webSocketDebuggerUrl: "ws://127.0.0.1:9222/a" }, target]), target);
  assert.throws(() => selectRendererTarget([{ type: "page", url: "https://example.com", webSocketDebuggerUrl: "ws://127.0.0.1:9222/a" }]), { code: "TARGET_NOT_FOUND" });
  assert.throws(() => selectRendererTarget([target, { ...target }]), { code: "TARGET_NOT_FOUND" });
});

test("debugger URL remains on the approved loopback listener", () => {
  const endpoint = validateEndpoint("http://127.0.0.1:9222");
  assert.equal(assertDebuggerUrl("ws://127.0.0.1:9222/devtools/page/1", endpoint), "ws://127.0.0.1:9222/devtools/page/1");
  assert.throws(() => assertDebuggerUrl("ws://example.com:9222/devtools/page/1", endpoint), { code: "CDP_ENDPOINT_REJECTED" });
  assert.throws(() => assertDebuggerUrl("ws://127.0.0.1:9333/devtools/page/1", endpoint), { code: "CDP_ENDPOINT_REJECTED" });
  assert.throws(() => assertDebuggerUrl("wss://127.0.0.1:9222/devtools/page/1", endpoint), { code: "CDP_ENDPOINT_REJECTED" });
});

test("listener verification binds current uid, exact app executable, and loopback address", () => {
  const listener = parseListenerOutput("p123\nu501\ncChatGPT\nn127.0.0.1:9222\n")[0];
  assert.deepEqual(
    verifyListenerIdentity(listener, "501 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT --remote-debugging-port=9222\n", 501),
    {
      pid: 123,
      owner_uid: 501,
      executable: "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT",
      loopback_only: true,
    },
  );
  assert.throws(
    () => verifyListenerIdentity({ ...listener, uid: 502 }, "501 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n", 501),
    { code: "CDP_LISTENER_UNVERIFIED" },
  );
  assert.throws(
    () => verifyListenerIdentity({ ...listener, names: ["*:9222"] }, "501 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n", 501),
    { code: "CDP_LISTENER_UNVERIFIED" },
  );
  assert.throws(
    () => verifyListenerIdentity(listener, "501 /Applications/Other.app/Contents/MacOS/Other\n", 501),
    { code: "CDP_LISTENER_UNVERIFIED" },
  );
});

test("listener verification accepts only inherited holders descended from ChatGPT", () => {
  const listeners = parseListenerOutput(
    "p123\nu501\ncChatGPT\nn127.0.0.1:9222\np456\nu501\ncHelper\nn127.0.0.1:9222\n",
  );
  const processes = [
    "123 1 501 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT --remote-debugging-port=9222",
    "456 123 501 /tmp/ChatGPT-child-helper",
  ].join("\n");
  assert.equal(parseProcessTable(processes).get(456).ppid, 123);
  assert.deepEqual(verifyListenerGroupIdentity(listeners, processes, 501), {
    pid: 123,
    owner_uid: 501,
    executable: "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT",
    loopback_only: true,
    inherited_listener_holders: 1,
    isolated_runner: false,
  });
  assert.throws(
    () => verifyListenerGroupIdentity(listeners, processes.replace("456 123", "456 1"), 501),
    { code: "CDP_LISTENER_UNVERIFIED" },
  );
  assert.throws(
    () => verifyListenerGroupIdentity(listeners, processes.replace("456 123 501", "456 123 0"), 501),
    { code: "CDP_LISTENER_UNVERIFIED" },
  );
});

test("default runner listener requires the exact isolated profile and port", () => {
  const listeners = parseListenerOutput("p123\nu501\ncChatGPT\nn127.0.0.1:9223\n");
  const command = `123 1 501 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT --user-data-dir=${RUNNER_PROFILE} --remote-debugging-address=127.0.0.1 --remote-debugging-port=9223`;
  assert.deepEqual(
    verifyListenerGroupIdentity(listeners, command, 501, { runnerProfile: RUNNER_PROFILE, runnerPort: 9223 }),
    {
      pid: 123,
      owner_uid: 501,
      executable: "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT",
      loopback_only: true,
      inherited_listener_holders: 0,
      isolated_runner: true,
    },
  );
  assert.throws(
    () => verifyListenerGroupIdentity(listeners, command.replace(`--user-data-dir=${RUNNER_PROFILE}`, "--user-data-dir=/tmp/other"), 501, { runnerProfile: RUNNER_PROFILE, runnerPort: 9223 }),
    { code: "CDP_LISTENER_UNVERIFIED" },
  );
});

function decodeRpc(value) {
  if (!Array.isArray(value)) {
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, decodeRpc(item)]));
    return value;
  }
  if (value.length === 1 && Array.isArray(value[0])) return value[0].map(decodeRpc);
  if (value[0] === "undefined") return undefined;
  if (value[0] === "bytes") return value[1];
  throw new Error(`unsupported test RPC value: ${String(value[0])}`);
}

function encodeRpc(value) {
  if (value === undefined || value === null || ["boolean", "number", "string"].includes(typeof value)) return value;
  if (value instanceof Uint8Array) return ["bytes", value];
  if (Array.isArray(value)) return [value.map(encodeRpc)];
  if (value && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, encodeRpc(item)]));
  }
  throw new Error("unsupported test RPC result");
}

function attachFakeAppHost(port, service, lifecycle = []) {
  const results = [null];
  let nextRemoteImportId = 1;
  const evaluate = (expression) => {
    let target = service;
    let parent = null;
    for (const part of expression[2]) { parent = target; target = target[part]; }
    const parameters = decodeRpc([expression[3]]);
    return target.apply(parent, parameters);
  };
  const encodeResult = async (value, resultId) => {
    if (!(value instanceof Response)) return { encoded: encodeRpc(value), pump: null };
    const pipeId = nextRemoteImportId++;
    port.postMessage(["pipe"]);
    const pump = async () => {
      const reader = value.body?.getReader();
      if (reader) {
        while (true) {
          const item = await reader.read();
          if (item.done) break;
          lifecycle.push(`body:${resultId}`);
          port.postMessage(["stream", ["pipeline", pipeId, ["write"], encodeRpc([item.value])[0]]]);
          nextRemoteImportId += 1;
        }
      }
      port.postMessage(["stream", ["pipeline", pipeId, ["close"], encodeRpc([])[0]]]);
      lifecycle.push(`body_closed:${resultId}`);
      nextRemoteImportId += 1;
    };
    return {
      encoded: ["response", ["readable", pipeId], {
        status: value.status,
        statusText: value.statusText,
        headers: [...value.headers],
      }],
      pump,
    };
  };
  port.addEventListener("message", async (event) => {
    const message = event.data;
    if (!Array.isArray(message)) return;
    if (message[0] === "push") {
      results.push(Promise.resolve().then(() => evaluate(message[1])));
    } else if (message[0] === "pull") {
      const value = await results[message[1]];
      let encoded;
      let pump = null;
      if (value && Object.hasOwn(value, "response")) {
        const response = await encodeResult(value.response, message[1]);
        encoded = { ...value, response: response.encoded };
        pump = response.pump;
      } else encoded = encodeRpc(value);
      port.postMessage(["resolve", message[1], encoded]);
      void pump?.();
    } else if (message[0] === "release") {
      lifecycle.push(`released:${message[1]}`);
    }
  });
  port.start();
}

test("current app-host HTTP RPC probes and streams without the legacy fetch bridge", async () => {
  const originalWindow = global.window;
  const bindingName = "__gptpro_test_binding";
  const hookName = "__gptpro_test_hook";
  const cancelled = [];
  const emissions = [];
  const lifecycle = [];
  const streamBodyChunks = [
    'data: {"type":"stream_handoff","turn_exchange_id":"turn-exchange-test"}\n\n',
    "data: [DONE]\n\n",
  ];
  let resolveComplete;
  const complete = new Promise((resolve) => { resolveComplete = resolve; });
  global[bindingName] = (payload) => {
    const value = JSON.parse(payload);
    emissions.push(value);
    if (value.type === "gptpro-http-complete") resolveComplete();
  };
  global.window = {
    location: { origin: "app://-" },
    postMessage(message, origin, ports) {
      assert.equal(message.type, "connect-app-host");
      assert.equal(origin, "app://-");
      attachFakeAppHost(ports[0], {
        services: {
          httpFetch: {
            cancel: async (id) => {
              cancelled.push(id);
              lifecycle.push(`cancelled:${id}`);
            },
            fetch: async (id, request) => {
              const chunks = request.url === "/f/conversation"
                ? streamBodyChunks
                : [JSON.stringify({ id, url: request.url, text: "한글 Markdown" })];
              return {
                response: new Response(new ReadableStream({
                  start(controller) {
                    const encoder = new TextEncoder();
                    let index = 0;
                    const write = () => {
                      controller.enqueue(encoder.encode(chunks[index++]));
                      if (index === chunks.length) controller.close();
                      else setTimeout(write, 5);
                    };
                    setTimeout(write, 5);
                  },
                }), {
                  status: 200,
                  headers: { "content-type": request.url === "/f/conversation" ? "text/event-stream" : "application/json" },
                }),
              };
            },
          },
        },
      }, lifecycle);
    },
  };
  let runtime;
  try {
    runtime = installAppHostHttpRuntime({ bindingName, hookName });
    assert.deepEqual(await runtime.probe(), { ok: true, contract: "app-host-http-v1", websocket_supported: true });
    const response = await runtime.request({ requestId: "request-1", method: "GET", url: "/models", headers: {}, body: undefined });
    assert.equal(response.status, 200);
    assert.deepEqual(JSON.parse(response.bodyText), { id: "request-1", url: "/models", text: "한글 Markdown" });
    assert.equal(runtime.startStream({ requestId: "stream-1", method: "POST", url: "/f/conversation", headers: {}, body: "{}" }), "stream-1");
    await complete;
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(emissions.map((item) => item.type), ["gptpro-http-response", "gptpro-http-chunk", "gptpro-http-chunk", "gptpro-http-complete"]);
    assert.equal(emissions.filter((item) => item.type === "gptpro-http-chunk").map((item) => item.data).join(""), streamBodyChunks.join(""));
    for (const closed of lifecycle.filter((item) => item.startsWith("body_closed:"))) {
      const id = closed.slice("body_closed:".length);
      const releaseIndex = lifecycle.indexOf(`released:${id}`);
      assert.notEqual(releaseIndex, -1);
      assert.ok(releaseIndex < lifecycle.indexOf(closed));
    }
    const bodyClosed = lifecycle.map((item, index) => item.startsWith("body_closed:") ? index : -1).filter((index) => index >= 0);
    assert.equal(bodyClosed.length, 2);
    assert.ok(lifecycle.indexOf("cancelled:request-1") > bodyClosed[0]);
    assert.ok(lifecycle.indexOf("cancelled:stream-1") > bodyClosed[1]);
    assert.ok(cancelled.some((id) => id.startsWith("gptpro-probe-")));
  } finally {
    await runtime?.close();
    delete global[bindingName];
    global.window = originalWindow;
  }
});

function catalogFixture() {
  return {
    default_model_slug: "gpt-pro-live",
    models: [
      { slug: "gpt-pro-live", title: "GPT Pro", max_tokens: 200000, configurable_thinking_effort: true, thinking_efforts: ["standard", "extended"] },
      { slug: "gpt-instant-live", title: "GPT Instant", max_tokens: 100000 },
    ],
    versions: [{ intelligence_presets: [
      { model_slug: "gpt-pro-live", thinking_effort: "standard" },
      { model_slug: "gpt-pro-live", thinking_effort: "extended" },
      { model_slug: "gpt-instant-live" },
    ] }],
  };
}

test("model catalog is dynamic and resolves exact effort without fallback", () => {
  const normalized = normalizeCatalog(catalogFixture());
  assert.equal(normalized.source, "dynamic");
  assert.deepEqual(normalized.models[0].thinking_efforts, ["standard", "extended"]);
  assert.equal(Object.hasOwn(normalized.models[0].capabilities, "local_functions"), false);
  assert.equal(Object.hasOwn(normalized.models[0].capabilities, "tools"), false);
  assert.equal(resolveModel(normalized, "gpt-pro-live", "extended").id, "gpt-pro-live");
  assert.throws(() => resolveModel(normalized, "GPT Pro", undefined), { code: "MODEL_NOT_FOUND" });
  assert.throws(() => resolveModel(normalized, "gpt-pro-live", "max"), { code: "MODEL_EFFORT_UNSUPPORTED" });
  assert.throws(() => normalizeCatalog({ models: [] }), { code: "MODEL_CATALOG_FAILED" });
  const unverified = normalizeCatalog({
    default_model_slug: "uncertain",
    models: [{ slug: "uncertain", title: "Uncertain", enabled_tools: ["tools"] }],
    versions: [{ intelligence_presets: [{ model_slug: "uncertain" }] }],
  });
  assert.equal(unverified.models[0].capabilities.server_tools, true);
  assert.equal(resolveModel(unverified, "uncertain", undefined).id, "uncertain");
  const disabled = normalizeCatalog({
    default_model_slug: "available",
    models: [
      { slug: "available", title: "Available" },
      { slug: "blocked", title: "Blocked" },
    ],
    categories: [
      { supported_models: ["available"] },
      { disabled_by_admin: true, supported_models: ["blocked"] },
    ],
  });
  assert.deepEqual(disabled.models.map((item) => item.id), ["available"]);
});

test("delta state reconstructs compact append operations", () => {
  const state = new DeltaState();
  assert.deepEqual(state.apply({ c: 0, p: "", o: "add", v: { text: "한글" } }), { text: "한글" });
  assert.deepEqual(state.apply({ p: "/text", o: "append", v: " Markdown" }), { text: "한글 Markdown" });
  assert.throws(() => state.apply({ c: 65, p: "", o: "add", v: {} }), { code: "STREAM_PROTOCOL_ERROR" });
  assert.throws(() => state.apply({ c: 0, p: "/__proto__/polluted", o: "add", v: true }), { code: "STREAM_PROTOCOL_ERROR" });
  assert.equal({}.polluted, undefined);
});

test("decoder assembles final text and reports zero tool routes", () => {
  const decoder = new ConversationDecoder();
  decoder.consume("plain", {
    conversation_id: "conversation-1",
    message: {
      id: "assistant-1",
      author: { role: "assistant" },
      recipient: "all",
      channel: "final",
      status: "finished_successfully",
      end_turn: true,
      content: { content_type: "text", parts: ["검토 완료"] },
      metadata: {
        content_references: [{ title: "후처리하면 안 되는 출처", url: "https://example.com/source" }],
      },
    },
  });
  const result = decoder.finish();
  assert.equal(result.text, "검토 완료");
  assert.equal(Object.hasOwn(result, "sources"), false);
  assert.equal(result.conversation_id, "conversation-1");
  assert.equal(result.tool_routes, 0);
  assert.equal(result.done, true);
});

test("decoder rejects every assistant recipient other than all and defers tool branch proof", () => {
  for (const recipient of ["local.repo_read", "functions.repo_read", "api_tool.list_resources", "search", "app.example"]) {
    const decoder = new ConversationDecoder();
    assert.throws(() => decoder.consume("plain", {
      message: {
        id: "external-1",
        author: { role: "assistant" },
        recipient,
        status: "finished_successfully",
        content: { content_type: "code", text: "{}" },
      },
    }), { code: "UNEXPECTED_TOOL_ROUTE", submissionState: "ambiguous" });
  }
  const decoder = new ConversationDecoder();
  assert.doesNotThrow(() => decoder.consume("plain", {
    message: {
      id: "tool-result-1",
      author: { role: "tool" },
      recipient: "all",
      content: { content_type: "text", parts: ["tool result"] },
    },
  }));
  assert.equal(decoder.toolRouteCandidate, true);
});

test("decoder waits for the recipient field on partial assistant deltas", () => {
  const decoder = new ConversationDecoder();
  assert.doesNotThrow(() => decoder.consume("plain", {
    message: {
      id: "assistant-partial",
      author: { role: "assistant" },
      channel: "final",
      status: "in_progress",
      content: { content_type: "text", parts: [""] },
    },
  }));
  decoder.consume("plain", {
    message: {
      id: "assistant-partial",
      author: { role: "assistant" },
      recipient: "all",
      channel: "final",
      status: "finished_successfully",
      end_turn: true,
      content: { content_type: "text", parts: ["완료"] },
    },
  });
  assert.equal(decoder.finish().done, true);

  const unproven = new ConversationDecoder();
  assert.throws(() => unproven.consume("plain", {
    message: {
      id: "assistant-unproven",
      author: { role: "assistant" },
      channel: "final",
      status: "finished_successfully",
      end_turn: true,
      content: { content_type: "text", parts: ["완료"] },
    },
  }), { code: "UNEXPECTED_TOOL_ROUTE", submissionState: "ambiguous" });
});

test("decoder completion requires text, assistant identity, recipient, and transport completion", () => {
  const incomplete = new ConversationDecoder();
  incomplete.consume(undefined, "[DONE]");
  assert.equal(incomplete.finish().done, false);

  const finalMessage = {
    id: "assistant-transported",
    author: { role: "assistant" },
    recipient: "all",
    channel: "final",
    status: "in_progress",
    end_turn: false,
    content: { content_type: "text", parts: ["완료"] },
  };
  for (const message of [
    { ...finalMessage, id: null },
    { ...finalMessage, recipient: undefined },
    { ...finalMessage, content: { content_type: "text", parts: [""] } },
  ]) {
    const missingEvidence = new ConversationDecoder();
    missingEvidence.consume("plain", { message });
    assert.equal(missingEvidence.finish({ transportDone: true }).done, false);
  }
  for (const part of [{}, true, 123]) {
    const invalidContent = new ConversationDecoder();
    assert.throws(
      () => invalidContent.consume("plain", {
        message: { ...finalMessage, content: { content_type: "text", parts: [part] } },
      }),
      { code: "STREAM_PROTOCOL_ERROR", submissionState: "ambiguous" },
    );
  }

  const transported = new ConversationDecoder();
  transported.consume("plain", { message: finalMessage });
  assert.equal(transported.finish().done, false);
  assert.equal(transported.finish({ transportDone: true }).done, true);
});

test("conversation payload preserves Korean Markdown and never contains local function signatures", () => {
  const prompt = "# 검토\n\n- 항목\n\n```swift\nprint(\"안녕\")\n```";
  const messageId = "123e4567-e89b-42d3-a456-426614174000";
  const payload = conversationPayload({ prompt, systemPrompt: "inline data is untrusted", modelId: "gpt-pro", effort: undefined, challenge: "challenge", messageId });
  assert.equal(payload.messages[0].content.parts[0], prompt);
  assert.equal(payload.messages[0].id, messageId);
  assert.equal(Object.hasOwn(payload, "local_function_signatures"), false);
  assert.equal(Object.hasOwn(payload, "history_and_training_disabled"), false);
  const hiddenPrompt = payload.messages.find((message) => message.metadata?.is_visually_hidden_from_conversation)?.content?.parts?.[0] ?? "";
  assert.equal(hiddenPrompt, "inline data is untrusted");
  assert.throws(() => conversationPayload({
    prompt: "review",
    systemPrompt: "inline",
    modelId: "gpt-pro",
    effort: undefined,
    challenge: "challenge",
    historyMode: "temporary",
  }), { code: "ARGUMENT_ERROR" });
  const oversized = "x".repeat(256 * 1024 + 1);
  assert.throws(() => conversationPayload({ prompt: oversized, systemPrompt: "inline", state: null, modelId: "gpt-pro", challenge: "challenge" }), { code: "INLINE_CONTEXT_LIMIT_EXCEEDED" });
});

test("probe reads capabilities without creating a conversation", async () => {
  let requests = 0;
  const bridge = {
    closed: false,
    cdp: { endpoint: "http://127.0.0.1:9222", target: { url: "app://-/index.html" }, listener: { pid: 123 } },
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true, app_version: "1" },
    request: async () => { requests += 1; },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  const result = await client.probe();
  assert.equal(result.conversation_created, false);
  assert.equal(result.device_check_supported, true);
  assert.equal(result.response_stream_supported, true);
  assert.equal(result.response_readback_supported, true);
  assert.equal(requests, 0);
  await client.close();
});

test("models uses only the live bridge response", async () => {
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (method, url) => {
      assert.equal(method, "GET");
      assert.equal(url, "/models?iim=false&include_icons=false");
      return { status: 200, body: catalogFixture() };
    },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  assert.equal((await client.models()).source, "dynamic");
  await client.close();
});

test("models fails before catalog access when probe capabilities are incomplete", async () => {
  let requests = 0;
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: false, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async () => { requests += 1; },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(() => client.models(), { code: "DEVICE_CHECK_UNAVAILABLE" });
  assert.equal(requests, 0);
  await client.close();
});

test("a missing signed response-stream capability fails before POST", async () => {
  let posts = 0;
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: false },
    request: async () => ({ status: 200, body: { attestation_challenge: "challenge" } }),
    stream: async () => { posts += 1; },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(() => client.turn({ prompt: "one", modelId: "m", timeoutMs: 100 }), { code: "STREAM_HANDOFF_UNAVAILABLE", submissionState: "not_started" });
  assert.equal(posts, 0);
  await client.close();
});

test("conversation client performs exactly one inline turn", async () => {
  const client = new PrivateConversationClient();
  let turn = 0;
  client.turn = async (options) => {
    turn += 1;
    options.onSubmitted({ request_id: "one" });
    return { text: "완료", commentary: "", sources: [], conversation_id: "c", parent_message_id: "a", assistant_message_id: "a", tool_routes: 0 };
  };
  const events = [];
  const result = await client.run({ prompt: "review", modelId: "m", historyMode: "normal", onEvent: (event) => events.push(event) });
  assert.equal(result.text, "완료");
  assert.equal(turn, 1);
  assert.deepEqual(events, [{ type: "submitted", request_id: "one" }]);
});

test("POST dispatch ambiguity is never automatically retried", async () => {
  let streams = 0;
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async () => ({ status: 200, body: { attestation_challenge: "challenge" } }),
    stream: async () => { streams += 1; const error = new Error("ambiguous"); error.code = "SUBMISSION_AMBIGUOUS"; throw error; },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(() => client.turn({ prompt: "one", state: null, modelId: "m", timeoutMs: 1000 }), { code: "SUBMISSION_AMBIGUOUS" });
  assert.equal(streams, 1);
  await client.close();
});

function handoffStream(topicId, onCancel = () => {}, prelude = [], encoded = false, handoffEvent = "message") {
  let release;
  const released = new Promise((resolve) => { release = resolve; });
  async function* events() {
    yield { type: "fetch-stream-response", status: 200, headers: { "content-type": "text/event-stream; charset=utf-8" } };
    if (encoded) yield { type: "fetch-stream-event", event: "delta_encoding", data: "v1" };
    for (const [channel, value] of prelude.entries()) {
      yield {
        type: "fetch-stream-event",
        event: encoded ? "delta" : "message",
        data: encoded ? { c: channel, p: "", o: "add", v: value } : value,
      };
      if (encoded && value?.message?.author?.role === "tool") {
        yield { type: "fetch-stream-event", event: "delta", data: { p: "/message/recipient", o: "add", v: "all" } };
      }
    }
    yield { type: "fetch-stream-event", event: handoffEvent, data: {
      type: "stream_handoff",
      turn_exchange_id: "turn-exchange-1",
      options: [{ type: "subscribe_ws_topic", topic_id: topicId }],
    } };
    await released;
  }
  return {
    requestId: "request",
    events: { [Symbol.asyncIterator]: events },
    cancel: async () => { onCancel(); release(); },
  };
}

function fakeHandoffSocket(topicId, text = "완료", recipient = "all", messageOverrides = {}, onDone = () => {}) {
  const sent = [];
  let closes = 0;
  const encoded = `event: plain\ndata: ${JSON.stringify({
    conversation_id: "conversation",
    message: {
      id: "assistant-message",
      author: { role: "assistant" },
      recipient,
      channel: "final",
      status: "finished_successfully",
      end_turn: true,
      content: { content_type: "text", parts: [text] },
      ...messageOverrides,
    },
  })}\n\n`;
  async function* events() {
    yield JSON.stringify({ id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: true, catchups: [] } });
    yield JSON.stringify({
      type: "message",
      topic_id: topicId,
      offset: "1",
      payload: { type: "conversation-turn-stream", payload: { type: "heartbeat", conversation_id: null, turn_id: "turn-1" } },
    });
    yield JSON.stringify({
      type: "message",
      topic_id: topicId,
      payload: {
        type: "conversation-turn-stream",
        payload: {
          type: "stream-item",
          conversation_id: "conversation",
          turn_id: "turn-1",
          stream_item_id: "item-1",
          parent_stream_item_id: null,
          encoded_item: encoded,
        },
      },
    });
    yield JSON.stringify({
      type: "message",
      topic_id: topicId,
      payload: { type: "conversation-turn-stream", payload: { type: "done", conversation_id: "conversation", turn_id: "turn-1" } },
    });
    onDone();
  }
  return {
    sent,
    get closes() { return closes; },
    events: { [Symbol.asyncIterator]: events },
    send: async (value) => sent.push(value),
    close: async () => { closes += 1; },
  };
}

test("stream handoff requires one recovered topic and hashes it without exposure", async () => {
  assert.equal(handoffTopic({ type: "other" }), null);
  assert.equal(
    handoffTopic({ type: "stream_handoff", turn_exchange_id: "exchange", options: [{ type: "subscribe_ws_topic", topic_id: "conversation-secret-topic" }] }),
    "conversation-secret-topic",
  );
  assert.equal(topicHash("conversation-secret-topic").length, 64);
  assert.throws(
    () => handoffTopic({ type: "stream_handoff", options: [{ type: "subscribe_ws_topic", topic_id: "conversation-missing-turn" }] }),
    { code: "STREAM_HANDOFF_INVALID", submissionState: "ambiguous" },
  );
  assert.throws(
    () => handoffTopic({ type: "stream_handoff", turn_exchange_id: "exchange", options: [{ type: "subscribe_ws_topic", topic_id: "wrong-prefix" }] }),
    { code: "STREAM_HANDOFF_INVALID", submissionState: "ambiguous" },
  );
  assert.throws(
    () => handoffTopic({ type: "stream_handoff", turn_exchange_id: "exchange", options: [
      { type: "subscribe_ws_topic", topic_id: "conversation-a" },
      { type: "subscribe_ws_topic", topic_id: "conversation-b" },
    ] }),
    { code: "STREAM_HANDOFF_INVALID", submissionState: "ambiguous" },
  );

  const topicId = "conversation-not-recovered";
  const socket = {
    async *events() {
      yield JSON.stringify({ id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: false } });
    },
    send: async () => {},
    close: async () => {},
  };
  const handoff = await StreamHandoff.connect({ openWebSocket: async () => ({
    events: { [Symbol.asyncIterator]: socket.events },
    send: socket.send,
    close: socket.close,
  }) }, "wss://example.invalid/signed", topicId);
  await assert.rejects(handoff.events.next(), { code: "STREAM_HANDOFF_RECOVERY_FAILED", submissionState: "ambiguous" });
});

test("stream handoff consumes recovered catchups and rejects malformed stream items", async () => {
  const topicId = "conversation-catchup";
  const catchup = {
    type: "message",
    topic_id: topicId,
    offset: "1",
    payload: {
      type: "conversation-turn-stream",
      payload: {
        type: "stream-item",
        conversation_id: "conversation",
        turn_id: "turn-1",
        stream_item_id: "item-1",
        parent_stream_item_id: null,
        encoded_item: 'event: plain\ndata: {"conversation_id":"conversation"}\n\n',
      },
    },
  };
  const recoveredSocket = {
    events: {
      async *[Symbol.asyncIterator]() {
        yield JSON.stringify({ id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: true, last_offset: "1", catchups: [catchup] } });
        yield JSON.stringify({
          type: "message",
          topic_id: topicId,
          offset: "2",
          payload: { type: "conversation-turn-stream", payload: { type: "done", conversation_id: "conversation", turn_id: "turn-1" } },
        });
      },
    },
    send: async () => {},
    close: async () => {},
  };
  const recovered = await StreamHandoff.connect({ openWebSocket: async () => recoveredSocket }, "wss://ws.chatgpt.com/signed", topicId);
  assert.deepEqual(await recovered.events.next(), { value: { event: "plain", data: { conversation_id: "conversation" } }, done: false });
  assert.deepEqual(await recovered.events.next(), { value: undefined, done: true });
  assert.equal(recovered.completed, true);

  for (const encodedItem of ["not-sse", catchup.payload.payload.encoded_item + "data: {private-broken-json\n\n"]) {
    const malformedSocket = {
      events: {
        async *[Symbol.asyncIterator]() {
          yield JSON.stringify({ id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: true, catchups: [] } });
          yield JSON.stringify({
            ...catchup,
            payload: {
              type: "conversation-turn-stream",
              payload: { ...catchup.payload.payload, encoded_item: encodedItem },
            },
          });
        },
      },
      send: async () => {},
      close: async () => {},
    };
    const malformed = await StreamHandoff.connect({ openWebSocket: async () => malformedSocket }, "wss://ws.chatgpt.com/signed", topicId);
    await assert.rejects(malformed.events.next(), { code: "STREAM_PROTOCOL_ERROR", submissionState: "ambiguous" });
    assert.equal(malformed.completed, false);
  }
});

test("SSE decoding rejects mixed valid and malformed JSON without leaking the payload", () => {
  const valid = 'event: plain\ndata: {"conversation_id":"conversation"}\n\n';
  assert.throws(
    () => parseSse(valid + 'data: {private-broken-json\n\n'),
    (error) => error.code === "STREAM_PROTOCOL_ERROR"
      && error.submissionState === "ambiguous"
      && !error.message.includes("private-broken-json"),
  );
  assert.deepEqual(parseSse(': keepalive\n\n' + valid + 'data: [DONE]\n\n'), [
    { event: "plain", data: { conversation_id: "conversation" } },
    { event: undefined, data: "[DONE]" },
  ]);
});

test("stream handoff rejects a sanitized encoded response error immediately", async () => {
  const topicId = "conversation-error";
  const socket = {
    events: {
      async *[Symbol.asyncIterator]() {
        yield JSON.stringify({ id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: true, catchups: [] } });
        yield JSON.stringify({
          type: "message",
          topic_id: topicId,
          payload: {
            type: "conversation-turn-stream",
            payload: {
              type: "stream-item",
              conversation_id: "conversation",
              turn_id: "turn-1",
              stream_item_id: "item-error",
              parent_stream_item_id: null,
              encoded_item: 'data: {"error":"private backend detail"}\n\n',
            },
          },
        });
      },
    },
    send: async () => {},
    close: async () => {},
  };
  const handoff = await StreamHandoff.connect({ openWebSocket: async () => socket }, "wss://ws.chatgpt.com/signed", topicId);
  await assert.rejects(handoff.events.next(), (error) => (
    error.code === "STREAM_INTERRUPTED"
    && error.submissionState === "ambiguous"
    && !error.message.includes("private backend detail")
  ));
});

test("stream handoff applies the Desktop initial and idle deadlines", async () => {
  const topicId = "conversation-deadline";
  const stalledSocket = (frames) => {
    let release;
    const released = new Promise((resolve) => { release = resolve; });
    return {
      events: {
        async *[Symbol.asyncIterator]() {
          for (const frame of frames) yield JSON.stringify(frame);
          await released;
        },
      },
      send: async () => {},
      close: async () => release(),
    };
  };

  const initial = await StreamHandoff.connect(
    { openWebSocket: async () => stalledSocket([]) },
    "wss://ws.chatgpt.com/signed",
    topicId,
    { initialTimeoutMs: 5, idleTimeoutMs: 50 },
  );
  await assert.rejects(initial.events.next(), { code: "STREAM_HANDOFF_INITIAL_TIMEOUT", submissionState: "ambiguous" });

  const idle = await StreamHandoff.connect(
    { openWebSocket: async () => stalledSocket([
      { id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: true, catchups: [] } },
      { type: "message", topic_id: topicId, payload: { type: "conversation-turn-stream", payload: { type: "heartbeat", turn_id: "turn-1" } } },
    ]) },
    "wss://ws.chatgpt.com/signed",
    topicId,
    { initialTimeoutMs: 50, idleTimeoutMs: 5 },
  );
  await assert.rejects(idle.events.next(), { code: "STREAM_HANDOFF_IDLE_TIMEOUT", submissionState: "ambiguous" });
});

test("durable parent callback completes before the only POST begins", async () => {
  const order = [];
  const messageId = "123e4567-e89b-42d3-a456-426614174000";
  const topicId = "conversation-durable-boundary";
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (_method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      throw new Error(`unexpected request ${url}`);
    },
    stream: async () => {
      order.push("post");
      return handoffStream(topicId);
    },
    openWebSocket: async () => fakeHandoffSocket(topicId),
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await client.turn({
    prompt: "one",
    state: null,
    modelId: "m",
    messageId,
    timeoutMs: 1_000,
    pollIntervalMs: 1,
    stabilityMs: 0,
    onBeforeSubmit: async () => { order.push("durable-parent-boundary"); },
  });
  assert.deepEqual(order, ["durable-parent-boundary", "post"]);
  await client.close();
});

test("attestation failure is pre-POST and never opens a stream", async () => {
  let streams = 0;
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async () => ({ status: 503, body: null }),
    stream: async () => { streams += 1; },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({ prompt: "one", state: null, modelId: "m", timeoutMs: 1_000 }),
    { code: "DEVICE_CHECK_UNAVAILABLE" },
  );
  assert.equal(streams, 0);
  await client.close();
});

test("a non-SSE POST response is ambiguous and never resent", async () => {
  let posts = 0;
  let cancelled = 0;
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async () => ({ status: 200, body: { attestation_challenge: "challenge" } }),
    stream: async () => {
      posts += 1;
      async function* events() {
        yield { type: "fetch-stream-response", status: 200, headers: { "content-type": "application/json" } };
      }
      return { requestId: "request", events: { [Symbol.asyncIterator]: events }, cancel: async () => { cancelled += 1; } };
    },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({ prompt: "one", modelId: "m", timeoutMs: 1_000 }),
    { code: "STREAM_PROTOCOL_ERROR", submissionState: "ambiguous" },
  );
  assert.equal(posts, 1);
  assert.equal(cancelled, 1);
  await client.close();
});

test("consult rejects a direct completion without the required signed handoff", async () => {
  let posts = 0;
  let requests = 0;
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (_method, url) => {
      requests += 1;
      assert.equal(url, "/ios/attestation_challenge");
      return { status: 200, body: { attestation_challenge: "challenge" } };
    },
    stream: async () => {
      posts += 1;
      async function* events() {
        yield { type: "fetch-stream-response", status: 200, headers: { "content-type": "text/event-stream" } };
        yield { type: "fetch-stream-event", event: "plain", data: {
          conversation_id: "conversation",
          message: { id: "status", author: { role: "tool" }, recipient: "all", content: { content_type: "text", parts: [""] } },
        } };
        yield { type: "fetch-stream-event", event: "plain", data: {
          conversation_id: "conversation",
          message: {
            id: "assistant-message", author: { role: "assistant" }, recipient: "all", channel: "final",
            status: "finished_successfully", end_turn: true, content: { content_type: "text", parts: ["완료"] },
          },
        } };
        yield { type: "fetch-stream-complete" };
      }
      return { requestId: "request", events: { [Symbol.asyncIterator]: events }, cancel: async () => {} };
    },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({ prompt: "one", modelId: "m", timeoutMs: 1_000 }),
    { code: "STREAM_HANDOFF_MISSING", submissionState: "ambiguous" },
  );
  assert.equal(posts, 1);
  assert.equal(requests, 1);
  await client.close();
});

test("raw stream handoff is routed before compact delta decoding", async () => {
  const topicId = "conversation-topic-raw-first";
  let posts = 0;
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (_method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      throw new Error("unexpected request " + url);
    },
    stream: async () => {
      posts += 1;
      return handoffStream(topicId, () => {}, [], false, "delta");
    },
    openWebSocket: async () => fakeHandoffSocket(topicId, "raw first"),
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  const result = await client.turn({ prompt: "원문", modelId: "m", timeoutMs: 1_000 });
  assert.equal(result.text, "raw first");
  assert.equal(result.current_branch_proof_required, false);
  assert.equal(posts, 1);
  await client.close();
});

test("the initial handoff deadline distinguishes missing and incomplete POST bodies", async () => {
  for (const [receivedChunks, code] of [[0, "STREAM_BODY_TIMEOUT"], [1, "STREAM_HANDOFF_FRAME_TIMEOUT"]]) {
    let posts = 0;
    let release;
    const released = new Promise((resolve) => { release = resolve; });
    const bridge = {
      closed: false,
      environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
      request: async () => ({ status: 200, body: { attestation_challenge: "challenge" } }),
      stream: async () => {
        posts += 1;
        async function* events() {
          yield { type: "fetch-stream-response", status: 200, headers: { "content-type": "text/event-stream" } };
          await released;
        }
        return {
          requestId: "request",
          events: { [Symbol.asyncIterator]: events },
          receivedChunks,
          cancel: async () => release(),
        };
      },
      close: async () => {},
    };
    const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
    await assert.rejects(
      () => client.turn({ prompt: "one", modelId: "m", timeoutMs: 1_000, initialHandoffTimeoutMs: 5 }),
      { code, submissionState: "ambiguous" },
    );
    assert.equal(posts, 1);
    await client.close();
  }
});

test("primary consultation uses one POST and the signed stream handoff", async () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174001";
  const topicId = "conversation-topic-1";
  const order = [];
  let posts = 0;
  let cancelled = 0;
  let signedDone = false;
  const socket = fakeHandoffSocket(
    topicId,
    "자동 회수 완료",
    "all",
    { status: "in_progress", end_turn: false },
    () => { signedDone = true; },
  );
  const detail = conversationDetail(messageId, "원문", "자동 회수 완료");
  detail.mapping["pro-status-node"] = {
    id: "pro-status-node",
    parent: "user-node",
    children: [],
    message: {
      id: "pro-status-message",
      author: { role: "tool", name: "opaque-pro-status" },
      recipient: "all",
      channel: null,
      status: "finished_successfully",
      end_turn: null,
      content: { content_type: "text", parts: [""] },
    },
  };
  detail.mapping["user-node"].children.push("pro-status-node");
  const prelude = [{ conversation_id: "conversation", message: detail.mapping["pro-status-node"].message }];
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (method, url) => {
      order.push(url);
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      if (url === "/conversation/conversation") {
        assert.equal(method, "GET");
        assert.equal(signedDone, true);
        return { status: 200, body: detail };
      }
      throw new Error(`unexpected request ${url}`);
    },
    stream: async () => {
      posts += 1;
      order.push("post");
      return handoffStream(topicId, () => { cancelled += 1; }, prelude, true);
    },
    openWebSocket: async (url) => {
      order.push("socket");
      assert.equal(url, "wss://ws.chatgpt.com/signed");
      return socket;
    },
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  const progress = [];
  const result = await client.turn({
    prompt: "원문",
    modelId: "m",
    messageId,
    timeoutMs: 1_000,
    onProgress: (event) => progress.push(event.stage),
  });
  assert.equal(result.text, "자동 회수 완료");
  assert.equal(result.completion_source, "signed-stream-handoff-v1");
  assert.equal(result.stream_handoff_topic_sha256, topicHash(topicId));
  assert.equal(result.current_branch_proof, "authenticated-exact-message-readback-v1");
  assert.equal(result.current_branch_proof_required, true);
  assert.equal(result.tool_route_candidate_observed, true);
  assert.equal(result.pre_handoff_assistant_observed, false);
  assert.equal(result.signed_delta_continuation_observed, false);
  assert.equal(result.signed_assistant_evidence, true);
  assert.equal(posts, 1);
  assert.equal(cancelled, 1);
  assert.deepEqual(order, ["/ios/attestation_challenge", "post", "/celsius/ws/user", "socket", "/conversation/conversation"]);
  assert.deepEqual(progress.slice(-3), ["stream_handoff", "current_branch_proof", "complete"]);
  const subscription = JSON.parse(socket.sent[0]);
  assert.deepEqual(subscription[1].command, { type: "subscribe", topic_id: topicId, offset: "0" });
  await client.close();
});

test("signed completion rejects a mismatched exact current branch without resend", async () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174006";
  const topicId = "conversation-topic-mismatch";
  let posts = 0;
  const prelude = [{
    conversation_id: "conversation",
    message: { id: "status", author: { role: "tool" }, content: { content_type: "text", parts: [""] } },
  }];
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      if (url === "/conversation/conversation") return { status: 200, body: conversationDetail(messageId, "원문", "다른 응답") };
      throw new Error(`unexpected request ${url}`);
    },
    stream: async () => {
      posts += 1;
      return handoffStream(topicId, () => {}, prelude, true);
    },
    openWebSocket: async () => fakeHandoffSocket(topicId, "signed 응답", "all", { status: "in_progress", end_turn: false }),
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({ prompt: "원문", modelId: "m", messageId, timeoutMs: 1_000 }),
    { code: "STREAM_BRANCH_MISMATCH", submissionState: "ambiguous" },
  );
  assert.equal(posts, 1);
  await client.close();
});

test("signed outer done cannot import a final assistant seen only before handoff", async () => {
  const topicId = "conversation-topic-no-signed-assistant";
  let posts = 0;
  const prelude = [{
    conversation_id: "conversation",
    message: {
      id: "prelude-assistant", author: { role: "assistant" }, recipient: "all", channel: "final",
      status: "finished_successfully", end_turn: true, content: { content_type: "text", parts: ["prelude only"] },
    },
  }];
  const socket = {
    events: {
      async *[Symbol.asyncIterator]() {
        yield JSON.stringify({ id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: true, catchups: [] } });
        yield JSON.stringify({
          type: "message", topic_id: topicId,
          payload: { type: "conversation-turn-stream", payload: { type: "done", conversation_id: "conversation", turn_id: "turn-1" } },
        });
      },
    },
    send: async () => {},
    close: async () => {},
  };
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (_method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      throw new Error(`unexpected request ${url}`);
    },
    stream: async () => {
      posts += 1;
      return handoffStream(topicId, () => {}, prelude);
    },
    openWebSocket: async () => socket,
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({ prompt: "원문", modelId: "m", timeoutMs: 1_000 }),
    { code: "STREAM_INTERRUPTED", submissionState: "ambiguous" },
  );
  assert.equal(posts, 1);
  await client.close();
});

test("a signed metadata-only continuation must prove its pre-handoff response branch", async () => {
  const topicId = "conversation-topic-metadata-only";
  const messageId = "123e4567-e89b-42d3-a456-426614174009";
  const prelude = [{
    conversation_id: "conversation",
    message: {
      id: "assistant-message", author: { role: "assistant" }, recipient: "all", channel: "final",
      status: "finished_successfully", end_turn: true, content: { content_type: "text", parts: ["raw-only"] },
    },
  }];
  const encodedItem = 'event: delta\ndata: {"c":0,"p":"/message/metadata/signed_marker","o":"add","v":true}\n\n';
  const socket = {
    events: {
      async *[Symbol.asyncIterator]() {
        yield JSON.stringify({ id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: true, catchups: [] } });
        yield JSON.stringify({
          type: "message", topic_id: topicId, offset: "1",
          payload: { type: "conversation-turn-stream", payload: {
            type: "stream-item", conversation_id: "conversation", turn_id: "turn-1",
            stream_item_id: "item-1", parent_stream_item_id: null, encoded_item: encodedItem,
          } },
        });
        yield JSON.stringify({
          type: "message", topic_id: topicId, offset: "2",
          payload: { type: "conversation-turn-stream", payload: { type: "done", conversation_id: "conversation", turn_id: "turn-1" } },
        });
      },
    },
    send: async () => {},
    close: async () => {},
  };
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (_method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      if (url === "/conversation/conversation") return { status: 200, body: conversationDetail(messageId, "원문", "different") };
      throw new Error(`unexpected request ${url}`);
    },
    stream: async () => handoffStream(topicId, () => {}, prelude, true),
    openWebSocket: async () => socket,
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({ prompt: "원문", modelId: "m", messageId, timeoutMs: 1_000 }),
    { code: "STREAM_BRANCH_MISMATCH", submissionState: "ambiguous" },
  );
  await client.close();
});

test("signed continuation keeps compact delta state across the raw handoff", async () => {
  const topicId = "conversation-topic-delta-continuation";
  const messageId = "123e4567-e89b-42d3-a456-426614174008";
  const prelude = [{
    conversation_id: "conversation",
    message: {
      id: "assistant-message", author: { role: "assistant" }, recipient: "all", channel: "final",
      status: "in_progress", end_turn: false, content: { content_type: "text", parts: ["자동 "] },
    },
  }];
  const encodedItem = 'event: delta\ndata: {"c":0,"p":"/message/content/parts/0","o":"append","v":"완료"}\n\n';
  const socket = {
    events: {
      async *[Symbol.asyncIterator]() {
        yield JSON.stringify({ id: 2, reply: { type: "subscribe", topic_id: topicId, recovered: true, catchups: [] } });
        yield JSON.stringify({
          type: "message", topic_id: topicId, offset: "1",
          payload: { type: "conversation-turn-stream", payload: {
            type: "stream-item", conversation_id: "conversation", turn_id: "turn-1",
            stream_item_id: "item-1", parent_stream_item_id: null, encoded_item: encodedItem,
          } },
        });
        yield JSON.stringify({
          type: "message", topic_id: topicId, offset: "2",
          payload: { type: "conversation-turn-stream", payload: { type: "done", conversation_id: "conversation", turn_id: "turn-1" } },
        });
      },
    },
    send: async () => {},
    close: async () => {},
  };
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (_method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      if (url === "/conversation/conversation") return { status: 200, body: conversationDetail(messageId, "원문", "자동 완료") };
      throw new Error(`unexpected request ${url}`);
    },
    stream: async () => handoffStream(topicId, () => {}, prelude, true),
    openWebSocket: async () => socket,
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  const result = await client.turn({ prompt: "원문", modelId: "m", messageId, timeoutMs: 1_000 });
  assert.equal(result.text, "자동 완료");
  assert.equal(result.completion_source, "signed-stream-handoff-v1");
  assert.equal(result.tool_route_candidate_observed, false);
  assert.equal(result.current_branch_proof_required, true);
  assert.equal(result.current_branch_proof, "authenticated-exact-message-readback-v1");
  assert.equal(result.pre_handoff_assistant_observed, true);
  assert.equal(result.signed_delta_continuation_observed, true);
  assert.equal(result.signed_assistant_evidence, true);
  await client.close();
});

test("current-branch proof has its own bounded GET-only deadline", async () => {
  const topicId = "conversation-topic-proof-timeout";
  const messageId = "123e4567-e89b-42d3-a456-426614174010";
  let posts = 0;
  let details = 0;
  let lists = 0;
  const prelude = [{
    conversation_id: "conversation",
    message: { id: "status", author: { role: "tool" }, recipient: "all", content: { content_type: "text", parts: [""] } },
  }];
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      if (url.startsWith("/conversations?")) {
        lists += 1;
        return { status: 200, body: { items: [] } };
      }
      if (url === "/conversation/conversation") {
        assert.equal(method, "GET");
        details += 1;
        return details % 2 === 1
          ? { status: 404, body: null }
          : { status: 200, body: conversationDetail(messageId, "원문", "부분", { status: "in_progress", end_turn: false }) };
      }
      throw new Error("unexpected request " + url);
    },
    stream: async () => {
      posts += 1;
      return handoffStream(topicId, () => {}, prelude, true);
    },
    openWebSocket: async () => fakeHandoffSocket(topicId, "완료", "all", { status: "in_progress", end_turn: false }),
    close: async () => {},
  };
  const progress = [];
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({
      prompt: "원문",
      modelId: "m",
      messageId,
      timeoutMs: 1_000,
      branchProofTimeoutMs: 15,
      branchProofPollIntervalMs: 1,
      onProgress: (event) => progress.push(event.stage),
    }),
    (error) => (
      error.code === "CURRENT_BRANCH_PROOF_TIMEOUT"
      && error.submissionState === "ambiguous"
      && error.stage === "current_branch_proof"
      && error.recovery.includes("collect-response")
    ),
  );
  assert.equal(posts, 1);
  assert.equal(lists, 0);
  assert.ok(details > 1);
  assert.equal(progress.at(-1), "current_branch_proof");
  await client.close();
});

test("signed stream timeout is ambiguous and never resends", async () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174002";
  const topicId = "conversation-topic-timeout";
  let posts = 0;
  let cancelled = 0;
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (_method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      throw new Error(`unexpected request ${url}`);
    },
    stream: async () => {
      posts += 1;
      return handoffStream(topicId, () => { cancelled += 1; });
    },
    openWebSocket: async (_url, options) => ({
      events: {
        async *[Symbol.asyncIterator]() {
          await new Promise((_resolve, reject) => options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true }));
        },
      },
      send: async () => {},
      close: async () => {},
    }),
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({ prompt: "one", modelId: "m", messageId, timeoutMs: 25 }),
    (error) => error.code === "TIMEOUT" && error.submissionState === "ambiguous" && error.stage === "stream_handoff",
  );
  assert.equal(posts, 1);
  assert.equal(cancelled, 1);
  await client.close();
});

test("primary signed stream rejects a prohibited tool route", async () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174003";
  const topicId = "conversation-topic-tool";
  let posts = 0;
  const socket = fakeHandoffSocket(topicId, "금지된 경로", "browser.search");
  const bridge = {
    closed: false,
    environment: { language: "ko", device_id: "device", device_check_supported: true, desktop_environment_readable: true, stream_bridge: true, websocket_bridge: true },
    request: async (_method, url) => {
      if (url === "/ios/attestation_challenge") return { status: 200, body: { attestation_challenge: "challenge" } };
      if (url === "/celsius/ws/user") return { status: 200, body: { websocket_url: "wss://ws.chatgpt.com/signed" } };
      throw new Error(`unexpected request ${url}`);
    },
    stream: async () => {
      posts += 1;
      return handoffStream(topicId);
    },
    openWebSocket: async () => socket,
    close: async () => {},
  };
  const client = new PrivateConversationClient({ bridgeFactory: async () => bridge });
  await assert.rejects(
    () => client.turn({ prompt: "one", modelId: "m", messageId, timeoutMs: 1_000 }),
    { code: "UNEXPECTED_TOOL_ROUTE", submissionState: "ambiguous" },
  );
  assert.equal(posts, 1);
  await client.close();
});

test("readback binds deterministic message ID, exact outbound, and final status", () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174002";
  const result = responseFromConversation(conversationDetail(messageId, "원문", "회수 완료"), { messageId, prompt: "원문" });
  assert.equal(result.text, "회수 완료");
  assert.equal(result.completion_source, "conversation-readback-v1");
  assert.equal(result.tool_routes, 0);
  assert.throws(
    () => responseFromConversation(conversationDetail(messageId, "변조됨"), { messageId, prompt: "원문" }),
    { code: "RESPONSE_CORRELATION_MISMATCH" },
  );
  assert.deepEqual(
    responseFromConversation(conversationDetail(messageId, "원문", "부분", { status: "in_progress", end_turn: false }), { messageId, prompt: "원문" }),
    { pending: true },
  );
  assert.throws(
    () => responseFromConversation(conversationDetail(messageId, "원문", "완료", { recipient: undefined }), { messageId, prompt: "원문" }),
    { code: "UNEXPECTED_TOOL_ROUTE" },
  );

  const duplicate = conversationDetail(messageId, "원문", "완료");
  duplicate.mapping["assistant-node"].message.id = messageId;
  assert.throws(
    () => responseFromConversation(duplicate, { messageId, prompt: "원문" }),
    { code: "RESPONSE_CORRELATION_AMBIGUOUS" },
  );

  const extraUserPart = conversationDetail(messageId, "원문", "완료");
  extraUserPart.mapping["user-node"].message.content.parts.push("추가");
  assert.throws(
    () => responseFromConversation(extraUserPart, { messageId, prompt: "원문" }),
    { code: "RESPONSE_CORRELATION_MISMATCH" },
  );

  const extraAssistantPart = conversationDetail(messageId, "원문", "완료");
  extraAssistantPart.mapping["assistant-node"].message.content.parts.push("추가");
  assert.throws(
    () => responseFromConversation(extraAssistantPart, { messageId, prompt: "원문" }),
    { code: "RESPONSE_READBACK_CONTRACT_CHANGED" },
  );
});

test("readback rejects a tool route in the matched branch", () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174003";
  assert.throws(
    () => responseFromConversation(conversationDetail(messageId, "원문", "도구", { recipient: "local.repo_read" }), { messageId, prompt: "원문" }),
    { code: "UNEXPECTED_TOOL_ROUTE" },
  );
  const detail = conversationDetail(messageId, "원문", "완료");
  detail.mapping["tool-node"] = {
    id: "tool-node",
    parent: "user-node",
    children: ["assistant-node"],
    message: { id: "tool-message", author: { role: "tool" }, recipient: "all", content: { content_type: "text", parts: [""] } },
  };
  detail.mapping["user-node"].children = ["tool-node"];
  detail.mapping["assistant-node"].parent = "tool-node";
  assert.throws(
    () => responseFromConversation(detail, { messageId, prompt: "원문" }),
    { code: "UNEXPECTED_TOOL_ROUTE" },
  );
});

test("readback is bounded to the matched user turn and rejects branch cycles", () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174007";
  const detail = conversationDetail(messageId, "원문", "첫 응답");
  detail.mapping["assistant-node"].children = ["later-user-node"];
  detail.mapping["later-user-node"] = {
    id: "later-user-node", parent: "assistant-node", children: ["later-assistant-node"],
    message: { id: "later-user", author: { role: "user" }, recipient: "all", content: { content_type: "text", parts: ["후속 질문"] } },
  };
  detail.mapping["later-assistant-node"] = {
    id: "later-assistant-node", parent: "later-user-node", children: [],
    message: {
      id: "later-assistant", author: { role: "assistant" }, recipient: "all", channel: "final",
      status: "finished_successfully", end_turn: true, content: { content_type: "text", parts: ["후속 응답"] },
    },
  };
  detail.current_node = "later-assistant-node";
  assert.equal(responseFromConversation(detail, { messageId, prompt: "원문" }).text, "첫 응답");

  const advanced = structuredClone(detail);
  advanced.mapping["assistant-node"].message.author.role = "system";
  assert.throws(
    () => responseFromConversation(advanced, { messageId, prompt: "원문" }),
    { code: "RESPONSE_CORRELATION_MISMATCH", submissionState: "ambiguous" },
  );

  const cyclic = conversationDetail(messageId, "원문", "완료");
  cyclic.mapping["assistant-node"].parent = "assistant-node";
  assert.throws(
    () => responseFromConversation(cyclic, { messageId, prompt: "원문" }),
    { code: "RESPONSE_READBACK_CONTRACT_CHANGED", submissionState: "ambiguous" },
  );
});

test("readback polls bounded summaries and returns the matched conversation ID", async () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174004";
  let lists = 0;
  const bridge = {
    request: async (method, url) => {
      if (url.startsWith("/conversations?")) {
        lists += 1;
        return { status: 200, body: { items: [{ id: "conversation", update_time: new Date().toISOString() }] } };
      }
      assert.equal(url, "/conversation/conversation");
      return { status: 200, body: conversationDetail(messageId, "원문", "완료") };
    },
  };
  const result = await waitForConversationResponse(bridge, {
    headers: {}, messageId, prompt: "원문", notBeforeMs: Date.now(), pollIntervalMs: 1,
  });
  assert.equal(lists, 1);
  assert.equal(result.conversation_id, "conversation");
  assert.equal(result.text, "완료");
});

test("known conversation branch verification polls persistence without listing", async () => {
  const messageId = "123e4567-e89b-42d3-a456-426614174005";
  let details = 0;
  const bridge = {
    request: async (_method, url) => {
      assert.equal(url, "/conversation/conversation");
      details += 1;
      return details === 1
        ? { status: 404, body: null }
        : { status: 200, body: conversationDetail(messageId, "원문", "완료") };
    },
  };
  const result = await waitForConversationResponse(bridge, {
    headers: {}, messageId, prompt: "원문", conversationId: "conversation", pollIntervalMs: 1, requestTimeoutMs: 100,
  });
  assert.equal(result.text, "완료");
  assert.equal(details, 2);
});

test("bridge request cancellation and stream timeout are surfaced and cleaned up", async () => {
  class FakeCdp extends EventEmitter {
    constructor() { super(); this.target = { url: "app://-/index.html" }; }
    async evaluate(value) { if (value.includes(".request(")) return new Promise(() => {}); }
    async send() {}
    async close() {}
  }
  const cdp = new FakeCdp();
  const bridge = new PrivateDesktopBridge(cdp, "binding", "hook", {});
  const aborter = new AbortController();
  const request = bridge.request("GET", "/models", { signal: aborter.signal, timeoutMs: 1_000 });
  aborter.abort();
  await assert.rejects(request, { code: "CANCELLED" });
  assert.equal(bridge.pending.size, 0);

  const counted = await bridge.stream("POST", "/f/conversation", { timeoutMs: 1_000 });
  cdp.emit("binding", {
    name: "binding",
    payload: JSON.stringify({ marker: "gptpro-app-host-http-v1", type: "gptpro-http-chunk", requestId: counted.requestId, data: "data: partial" }),
  });
  assert.equal(counted.receivedChunks, 1);
  await counted.cancel();

  const malformed = await bridge.stream("POST", "/f/conversation", { timeoutMs: 1_000 });
  assert.doesNotThrow(() => cdp.emit("binding", {
    name: "binding",
    payload: JSON.stringify({
      marker: "gptpro-app-host-http-v1", type: "gptpro-http-chunk", requestId: malformed.requestId,
      data: 'data: {"message":"valid"}\n\ndata: {private-broken-json\n\n',
    }),
  }));
  await assert.rejects(malformed.events.next(), { code: "STREAM_PROTOCOL_ERROR", submissionState: "ambiguous" });
  assert.equal(bridge.pending.size, 0);

  const stream = await bridge.stream("POST", "/f/conversation", { timeoutMs: 10 });
  await assert.rejects(stream.events[Symbol.asyncIterator]().next(), { code: "TIMEOUT" });
  assert.equal(bridge.pending.size, 0);

  const sentinel = "/conversation/RAW_SENTINEL";
  await assert.rejects(
    bridge.request("GET", sentinel, { timeoutMs: 5 }),
    (error) => {
      const serialized = JSON.stringify({ ok: false, error: sanitizedError(error) });
      return (
        error.code === "TIMEOUT"
        && !error.message.includes(sentinel)
        && !error.message.includes("RAW_SENTINEL")
        && !serialized.includes(sentinel)
        && !serialized.includes("RAW_SENTINEL")
      );
    },
  );
  assert.equal(bridge.pending.size, 0);
  await bridge.close();
});

test("bridge renderer WebSocket forwards text and removes its listener state", async () => {
  class FakeCdp extends EventEmitter {
    constructor() { super(); this.target = { url: "app://-/index.html" }; this.bridge = null; }
    async evaluate(expression) {
      if (expression.includes(".openSocket(")) {
        queueMicrotask(() => {
          const socketId = [...this.bridge.sockets.keys()][0];
          this.emit("binding", {
            name: "binding",
            payload: JSON.stringify({ marker: "gptpro-app-host-http-v1", type: "gptpro-ws-open", socketId }),
          });
        });
      }
      return true;
    }
    async send() {}
    async close() {}
  }
  const cdp = new FakeCdp();
  const bridge = new PrivateDesktopBridge(cdp, "binding", "hook", {});
  cdp.bridge = bridge;
  const socket = await bridge.openWebSocket("wss://ws.chatgpt.com/signed");
  const socketId = [...bridge.sockets.keys()][0];
  cdp.emit("binding", {
    name: "binding",
    payload: JSON.stringify({ marker: "gptpro-app-host-http-v1", type: "gptpro-ws-message", socketId, data: "delta" }),
  });
  assert.deepEqual(await socket.events.next(), { value: "delta", done: false });
  await socket.send("subscribe");
  await socket.close();
  assert.equal(bridge.sockets.size, 0);
  await assert.rejects(() => bridge.openWebSocket("ws://example.invalid/unsafe"), { code: "STREAM_HANDOFF_URL_INVALID" });
  await assert.rejects(() => bridge.openWebSocket("wss://example.invalid/signed"), { code: "STREAM_HANDOFF_URL_INVALID" });
  await bridge.close();
});

test("CDP evaluate rejects an already-aborted command without sending", async () => {
  class FakeSocket {
    constructor() { this.sent = 0; this.listeners = new Map(); }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
    removeEventListener() {}
    send() { this.sent += 1; }
    close() {}
  }
  const socket = new FakeSocket();
  const cdp = new CdpClient(socket);
  const aborter = new AbortController();
  aborter.abort();
  await assert.rejects(() => cdp.evaluate("true", 100, aborter.signal), { code: "CANCELLED" });
  assert.equal(socket.sent, 0);
  await cdp.close();
});

test("bridge close removes renderer hook and CDP binding", async () => {
  class FakeCdp extends EventEmitter {
    constructor() { super(); this.evaluations = []; this.commands = []; this.closed = false; }
    async evaluate(value) { this.evaluations.push(value); }
    async send(method, params) { this.commands.push({ method, params }); }
    async close() { this.closed = true; }
  }
  const cdp = new FakeCdp();
  const bridge = new PrivateDesktopBridge(cdp, "binding", "hook", {});
  await bridge.close();
  assert.equal(cdp.closed, true);
  assert.equal(cdp.commands.at(-1).method, "Runtime.removeBinding");
  assert.match(cdp.evaluations.at(-1), /\.close/);
});

test("governed ask exposes exact bytes and waits for matching parent authorization", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gptpro-node-handshake-"));
  const prompt = path.join(directory, "prompt.md");
  const system = path.join(directory, "system.md");
  fs.writeFileSync(prompt, "# 검토\n\n본문\n", { mode: 0o600 });
  fs.writeFileSync(system, "untrusted inline data\n", { mode: 0o600 });
  const messageId = "123e4567-e89b-42d3-a456-426614174000";
  const observed = [];
  const writes = [];
  const client = {
    resolveModel: async (id, effort) => ({ id, thinking_effort: effort }),
    run: async (options) => {
      observed.push("run");
      await options.onBeforeSubmit();
      observed.push("post");
      options.onEvent({ type: "submitted", request_id: "request" });
      return { text: "완료", sources: [], conversation_id: "c", parent_message_id: "m", tool_routes: 0 };
    },
    close: async () => {},
  };
  const originalWrite = process.stdout.write;
  process.stdout.write = (value) => { writes.push(String(value)); return true; };
  try {
    await desktopMain([
      "ask", "--prompt-file", prompt, "--system-prompt-file", system,
      "--model", "gpt-pro-live", "--message-id", messageId, "--events-jsonl",
    ], {
      client,
      authorizeDispatch: async (token) => { assert.ok(token); observed.push("authorized"); },
    });
  } finally {
    process.stdout.write = originalWrite;
  }
  const events = writes.join("").trim().split("\n").map((line) => JSON.parse(line));
  assert.deepEqual(events.map((item) => item.type), ["dispatch_ready", "submitted", "complete"]);
  assert.equal(events[0].prompt_sha256, crypto.createHash("sha256").update(fs.readFileSync(prompt)).digest("hex"));
  assert.equal(events[0].prompt_bytes, fs.statSync(prompt).size);
  assert.equal(events[0].system_prompt_sha256, crypto.createHash("sha256").update(fs.readFileSync(system)).digest("hex"));
  assert.equal(events[0].message_id, messageId);
  assert.deepEqual(observed, ["run", "authorized", "post"]);
  fs.rmSync(directory, { recursive: true, force: true });
});

test("governed collect performs readback without model resolution or POST", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gptpro-node-collect-"));
  const prompt = path.join(directory, "prompt.md");
  fs.writeFileSync(prompt, "승인된 원문\n", { mode: 0o600 });
  const messageId = "123e4567-e89b-42d3-a456-426614174005";
  let collects = 0;
  let posts = 0;
  const writes = [];
  const client = {
    resolveModel: async () => { throw new Error("collect must not resolve a model"); },
    run: async () => { posts += 1; },
    collect: async (options) => {
      collects += 1;
      assert.equal(options.messageId, messageId);
      assert.equal(options.prompt, "승인된 원문\n");
      options.onProgress({ type: "progress", stage: "response_readback" });
      return {
        text: "회수 완료",
        conversation_id: "conversation",
        parent_message_id: "assistant",
        tool_routes: 0,
        completion_source: "conversation-readback-v1",
      };
    },
    close: async () => {},
  };
  const originalWrite = process.stdout.write;
  process.stdout.write = (value) => { writes.push(String(value)); return true; };
  try {
    await desktopMain([
      "collect", "--prompt-file", prompt, "--message-id", messageId,
      "--not-before", "2026-09-03T11:47:00Z", "--events-jsonl",
    ], { client });
  } finally {
    process.stdout.write = originalWrite;
  }
  const events = writes.join("").trim().split("\n").map((line) => JSON.parse(line));
  assert.deepEqual(events.map((item) => item.type), ["progress", "complete"]);
  assert.equal(events.at(-1).completion_source, "conversation-readback-v1");
  assert.equal(collects, 1);
  assert.equal(posts, 0);
  fs.rmSync(directory, { recursive: true, force: true });
});

test("failed parent authorization prevents the Desktop POST", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gptpro-node-denied-"));
  const prompt = path.join(directory, "prompt.md");
  fs.writeFileSync(prompt, "review\n", { mode: 0o600 });
  let posts = 0;
  const client = {
    resolveModel: async (id) => ({ id }),
    run: async (options) => {
      await options.onBeforeSubmit();
      posts += 1;
    },
    close: async () => {},
  };
  const originalWrite = process.stdout.write;
  process.stdout.write = () => true;
  try {
    await assert.rejects(
      () => desktopMain([
        "ask", "--prompt-file", prompt, "--model", "gpt-pro-live", "--events-jsonl",
      ], {
        client,
        authorizeDispatch: async () => {
          const error = new Error("parent closed");
          error.code = "DISPATCH_AUTHORIZATION_MISSING";
          throw error;
        },
      }),
      { code: "DISPATCH_AUTHORIZATION_MISSING" },
    );
  } finally {
    process.stdout.write = originalWrite;
  }
  assert.equal(posts, 0);
  fs.rmSync(directory, { recursive: true, force: true });
});

test("removed and unknown ask options fail before POST", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gptpro-node-removed-tool-"));
  const prompt = path.join(directory, "prompt.md");
  const tools = path.join(directory, "tools.json");
  fs.writeFileSync(prompt, "review\n", { mode: 0o600 });
  fs.writeFileSync(tools, JSON.stringify([{ name: "gptpro_repo_read", params: [], type: "kwargs" }]), { mode: 0o600 });
  let runs = 0;
  const client = {
    resolveModel: async (id) => ({ id }),
    run: async () => { runs += 1; },
    close: async () => {},
  };
  const originalWrite = process.stdout.write;
  process.stdout.write = () => true;
  try {
    await assert.rejects(
      () => desktopMain(["ask", "--prompt-file", prompt, "--model", "gpt-pro-live"], { client }),
      { code: "ARGUMENT_ERROR", submissionState: "not_started" },
    );
    for (const option of [["--tools-file", tools], ["--output", path.join(directory, "response.md")], ["--state-file", path.join(directory, "state.json")]]) {
      await assert.rejects(
        () => desktopMain([
          "ask", "--prompt-file", prompt, "--model", "gpt-pro-live", ...option,
        ], { client }),
        { code: "ARGUMENT_ERROR", submissionState: "not_started" },
      );
    }
  } finally {
    process.stdout.write = originalWrite;
  }
  assert.equal(runs, 0);
  fs.rmSync(directory, { recursive: true, force: true });
});

test("ask rejects a prompt one byte above 256 KiB before model resolution", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gptpro-node-limit-"));
  const prompt = path.join(directory, "prompt.md");
  fs.writeFileSync(prompt, "x".repeat(256 * 1024 + 1), { mode: 0o600 });
  let resolutions = 0;
  const client = {
    resolveModel: async (id) => { resolutions += 1; return { id }; },
    run: async () => { throw new Error("must not run"); },
    close: async () => {},
  };
  const originalWrite = process.stdout.write;
  process.stdout.write = () => true;
  try {
    await assert.rejects(
      () => desktopMain([
        "ask", "--prompt-file", prompt, "--model", "gpt-pro-live",
        "--history-mode", "normal", "--events-jsonl",
      ], { client }),
      { code: "INLINE_CONTEXT_LIMIT_EXCEEDED", submissionState: "not_started" },
    );
  } finally {
    process.stdout.write = originalWrite;
  }
  assert.equal(resolutions, 0);
  fs.rmSync(directory, { recursive: true, force: true });
});
