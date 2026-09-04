"use strict";

const crypto = require("node:crypto");
const { PrivateDesktopBridge, headerRecord } = require("./private-bridge.js");
const { waitForConversationResponse } = require("./conversation-readback.js");
const { ConversationDecoder } = require("./delta-decoder.js");
const { normalizeCatalog, resolveModel } = require("./model-catalog.js");
const { runtimeError } = require("./errors.js");
const { handoffTopic, openStreamHandoff } = require("./stream-handoff.js");

const ATTACH_AUTH = "X-OpenAI-Attach-Auth";
const ATTACH_DESKTOP = "X-OpenAI-Attach-Desktop-Surface";
const ATTACH_DEVICE = "X-OpenAI-Attach-DeviceCheck-Token";
const ATTACH_INTEGRITY = "X-OpenAI-Attach-Integrity-State";
const MAX_PROMPT_BYTES = 256 * 1024;

function deadlineScope(upstreamSignal, timeoutMs, submissionRisk, currentStage, timeoutErrorFactory = null) {
  const controller = new AbortController();
  const forwardAbort = () => {
    const reason = upstreamSignal?.reason;
    controller.abort(
      reason && typeof reason === "object" && typeof reason.code === "string"
        ? reason
        : runtimeError("CANCELLED", "The Desktop consultation was cancelled.", {
          submissionState: submissionRisk() ? "ambiguous" : "not_started",
          stage: currentStage(),
        }),
    );
  };
  if (upstreamSignal?.aborted) forwardAbort();
  else upstreamSignal?.addEventListener("abort", forwardAbort, { once: true });
  const timer = setTimeout(() => {
    if (timeoutErrorFactory) {
      controller.abort(timeoutErrorFactory());
      return;
    }
    const submitted = submissionRisk();
    controller.abort(runtimeError("TIMEOUT", "The Desktop consultation exceeded its overall deadline.", {
      retryable: !submitted,
      submissionState: submitted ? "ambiguous" : "not_started",
      recovery: submitted
        ? "Inspect the existing conversation evidence. Do not resend this package automatically."
        : "Run desktop-doctor, then retry only while the exact package approval remains valid.",
      stage: currentStage(),
    }));
  }, timeoutMs);
  return {
    signal: controller.signal,
    close() {
      clearTimeout(timer);
      upstreamSignal?.removeEventListener("abort", forwardAbort);
    },
  };
}

function userMessage(text, messageId = crypto.randomUUID()) {
  return {
    id: messageId,
    author: { role: "user", name: null, metadata: {} },
    create_time: Date.now() / 1000,
    update_time: null,
    content: { content_type: "text", parts: [text] },
    status: "finished_successfully",
    end_turn: null,
    weight: 1,
    metadata: {},
    recipient: "all",
    channel: null,
  };
}

function systemMessage(text) {
  return {
    id: crypto.randomUUID(),
    author: { role: "system" },
    content: { content_type: "text", parts: [text] },
    metadata: { is_visually_hidden_from_conversation: true },
  };
}

function conversationPayload({ prompt, systemPrompt, modelId, effort, challenge, historyMode, messageId }) {
  const resolvedHistoryMode = historyMode ?? "normal";
  if (resolvedHistoryMode !== "normal") {
    throw runtimeError("ARGUMENT_ERROR", "Schema-6 inline consultations require normal Chat history mode.");
  }
  if (typeof prompt !== "string" || !prompt.trim()) {
    throw runtimeError("ARGUMENT_ERROR", "The inline consultation prompt must not be empty.");
  }
  if (Buffer.byteLength(prompt, "utf8") > MAX_PROMPT_BYTES) {
    throw runtimeError("INLINE_CONTEXT_LIMIT_EXCEEDED", `The inline consultation prompt exceeds ${MAX_PROMPT_BYTES} bytes.`);
  }
  const messages = [userMessage(prompt, messageId)];
  if (typeof systemPrompt === "string" && systemPrompt.trim()) messages.push(systemMessage(systemPrompt));
  return {
    action: "next",
    messages,
    model: modelId,
    supported_encodings: ["v1"],
    client_prepare_state: "none",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    timezone_offset_min: new Date().getTimezoneOffset(),
    app_attest_challenge: challenge,
    ...(effort ? { thinking_effort: effort } : {}),
  };
}

class PrivateConversationClient {
  constructor(options = {}) {
    this.options = options;
    this.bridge = null;
  }

  createBridge() {
    return (this.options.bridgeFactory ?? PrivateDesktopBridge.connect)(this.options);
  }

  async connect() {
    if (!this.bridge || this.bridge.closed) this.bridge = await this.createBridge();
    return this.bridge;
  }

  baseHeaders(bridge) {
    return {
      "OAI-Language": bridge.environment.language || "en",
      "oai-did": bridge.environment.device_id,
      [ATTACH_AUTH]: "1",
      [ATTACH_INTEGRITY]: "1",
      ...(bridge.environment.device_check_supported ? { [ATTACH_DESKTOP]: "1" } : {}),
    };
  }

  assertCapabilities(bridge) {
    if (bridge.environment.desktop_environment_readable !== true) {
      throw runtimeError("DESKTOP_CAPABILITY_UNAVAILABLE", "The ChatGPT Desktop environment capability is unavailable.");
    }
    if (bridge.environment.stream_bridge !== true) {
      throw runtimeError("BRIDGE_UNAVAILABLE", "The ChatGPT Desktop request/stream bridge is unavailable.");
    }
    if (bridge.environment.device_check_supported !== true) {
      throw runtimeError("DEVICE_CHECK_UNAVAILABLE", "The ChatGPT Desktop DeviceCheck capability is unavailable.");
    }
  }

  async probe() {
    const bridge = await this.connect();
    return {
      ok: true,
      channel: "desktop-electron",
      endpoint: bridge.cdp.endpoint,
      target_url: bridge.cdp.target.url,
      listener_pid: bridge.cdp.listener?.pid ?? null,
      isolated_runner: bridge.cdp.listener?.isolated_runner === true,
      desktop_bridge: true,
      desktop_environment_readable: bridge.environment.desktop_environment_readable === true,
      device_check_supported: bridge.environment.device_check_supported === true,
      stream_bridge: bridge.environment.stream_bridge === true,
      response_stream_supported: bridge.environment.websocket_bridge === true,
      response_readback_supported: true,
      bridge_contract: bridge.environment.bridge_contract ?? null,
      app_version: bridge.environment.app_version,
      conversation_created: false,
    };
  }

  async models(options = {}) {
    const bridge = await this.connect();
    this.assertCapabilities(bridge);
    const response = await bridge.request("GET", "/models?iim=false&include_icons=false", {
      headers: this.baseHeaders(bridge), signal: options.signal, timeoutMs: options.timeoutMs ?? 30_000,
    });
    if (response.status < 200 || response.status >= 300) throw runtimeError("MODEL_CATALOG_FAILED", `The logged-in model catalog returned HTTP ${response.status}.`);
    return normalizeCatalog(response.body);
  }

  async resolveModel(intent, effort, options = {}) {
    return resolveModel(await this.models(options), intent, effort);
  }

  async turn(options) {
    const timeoutMs = options.timeoutMs ?? 2_700_000;
    let submissionRisk = false;
    let stage = "preflight";
    const progress = (next) => {
      stage = next;
      options.onProgress?.({ type: "progress", stage: next });
    };
    const scope = deadlineScope(options.signal, timeoutMs, () => submissionRisk, () => stage);
    try {
      return await this.#turnWithinDeadline(
        { ...options, signal: scope.signal, timeoutMs, progress },
        () => { submissionRisk = true; },
      );
    } finally {
      scope.close();
    }
  }

  async #turnWithinDeadline(options, markSubmissionRisk) {
    const historyMode = options.historyMode ?? "normal";
    options.progress("preflight");
    const bridge = await this.connect();
    this.assertCapabilities(bridge);
    if (bridge.environment.websocket_bridge !== true) {
      throw runtimeError("STREAM_HANDOFF_UNAVAILABLE", "The ChatGPT Desktop signed response-stream capability is unavailable.");
    }
    const headers = this.baseHeaders(bridge);
    const challengeResponse = await bridge.request("GET", "/ios/attestation_challenge", {
      headers: { ...headers, [ATTACH_DEVICE]: "1" }, signal: options.signal, timeoutMs: Math.min(options.timeoutMs ?? 30_000, 30_000),
    });
    const challenge = challengeResponse.body?.attestation_challenge;
    if (challengeResponse.status < 200 || challengeResponse.status >= 300 || typeof challenge !== "string" || !challenge) {
      throw runtimeError("DEVICE_CHECK_UNAVAILABLE", "The Desktop attestation challenge is unavailable.");
    }
    const messageId = options.messageId ?? crypto.randomUUID();
    const payload = conversationPayload({ ...options, historyMode, challenge, messageId });
    options.progress("dispatch_ready");
    await options.onBeforeSubmit?.();
    options.progress("dispatch_authorized");
    let stream;
    markSubmissionRisk();
    try {
      stream = await bridge.stream("POST", "/f/conversation", {
        headers,
        body: JSON.stringify(payload),
        signal: options.signal,
        timeoutMs: options.timeoutMs ?? 2_700_000,
        format: "sse",
      });
    } catch (error) {
      if (error?.code === "SUBMISSION_AMBIGUOUS") throw error;
      throw runtimeError("SUBMISSION_AMBIGUOUS", "The conversation may have been submitted but no reliable stream handle was returned.", { cause: error, submissionState: "ambiguous" });
    }
    options.onSubmitted?.({ request_id: stream.requestId });
    options.progress("submitted");
    const iterator = stream.events[Symbol.asyncIterator]();
    let response;
    let handoff = null;
    let drainPromise = null;
    const decoder = new ConversationDecoder();
    try {
      while (true) {
        const item = await iterator.next();
        if (item.done) throw runtimeError("SUBMISSION_AMBIGUOUS", "The conversation stream ended before response headers.", { submissionState: "ambiguous" });
        if (item.value.type === "fetch-stream-response") {
          response = { status: Number(item.value.status), headers: headerRecord(item.value.headers) };
          options.progress("response_headers");
          break;
        }
      }
      if (response.status < 200 || response.status >= 300) {
        await stream.cancel(runtimeError("CONVERSATION_REJECTED", `The conversation request returned HTTP ${response.status}.`, { submissionState: "rejected" }));
        throw runtimeError("CONVERSATION_REJECTED", `The conversation request returned HTTP ${response.status}.`, { submissionState: "rejected" });
      }
      options.progress("response_stream");
      let topicId = null;
      let directComplete = false;
      while (!topicId && !directComplete) {
        const item = await iterator.next();
        if (item.done || item.value?.type === "fetch-stream-complete") {
          directComplete = true;
          break;
        }
        if (item.value?.type !== "fetch-stream-event") continue;
        const found = handoffTopic(item.value.data);
        if (found) {
          topicId = found;
          break;
        }
        decoder.consume(item.value.event, item.value.data);
      }

      let completionSource;
      let handoffTopicSha256 = null;
      if (topicId) {
        handoff = await openStreamHandoff(bridge, topicId, {
          headers,
          signal: options.signal,
          timeoutMs: Math.min(options.timeoutMs ?? 30_000, 30_000),
        });
        handoffTopicSha256 = handoff.topicSha256;
        drainPromise = (async () => {
          while (true) {
            const item = await iterator.next();
            if (item.done || item.value?.type === "fetch-stream-complete") return;
          }
        })();
        void drainPromise.catch(() => {});
        for await (const event of handoff.events) decoder.consume(event.event, event.data);
        completionSource = "signed-stream-handoff-v1";
      } else {
        completionSource = "direct-desktop-stream-v1";
      }

      const result = decoder.finish();
      if (result.done !== true) {
        throw runtimeError("STREAM_INTERRUPTED", "The Desktop response stream ended without a completed assistant turn.", { submissionState: "ambiguous" });
      }
      await stream.cancel(runtimeError("CANCELLED", "The completed Desktop response stream was released.", { submissionState: "ambiguous" }));
      if (drainPromise) await drainPromise.catch(() => {});
      options.progress("complete");
      return {
        ...result,
        done: true,
        completion_source: completionSource,
        stream_handoff_topic_sha256: handoffTopicSha256,
      };
    } catch (error) {
      await stream.cancel(error);
      if (drainPromise) await drainPromise.catch(() => {});
      if (error?.code) throw error;
      throw runtimeError("SUBMISSION_AMBIGUOUS", "The Desktop response stream could not be proven complete; the prompt will not be resent.", { cause: error, submissionState: "ambiguous" });
    } finally {
      await handoff?.close().catch(() => {});
    }
  }

  async run(options) {
    return this.turn({
      prompt: options.prompt,
      systemPrompt: options.systemPrompt,
      modelId: options.modelId,
      effort: options.effort,
      historyMode: options.historyMode,
      signal: options.signal,
      timeoutMs: options.timeoutMs,
      messageId: options.messageId,
      onBeforeSubmit: options.onBeforeSubmit,
      onProgress: options.onProgress,
      onSubmitted: (event) => options.onEvent?.({ type: "submitted", ...event }),
    });
  }

  async collect(options) {
    let stage = "response_readback";
    const scope = deadlineScope(
      options.signal,
      options.timeoutMs ?? 600_000,
      () => true,
      () => stage,
      () => runtimeError("RESPONSE_COLLECTION_TIMEOUT", "Authenticated response readback did not complete before its deadline.", {
        retryable: true,
        submissionState: "ambiguous",
        recovery: "Retry collect-response. It performs GET readback only and never resends the prompt.",
        stage,
      }),
    );
    try {
      const bridge = await this.connect();
      this.assertCapabilities(bridge);
      options.onProgress?.({ type: "progress", stage });
      const result = await waitForConversationResponse(bridge, {
        headers: this.baseHeaders(bridge),
        messageId: options.messageId,
        prompt: options.prompt,
        notBeforeMs: options.notBeforeMs ?? Date.now(),
        signal: scope.signal,
        pollIntervalMs: options.pollIntervalMs,
      });
      stage = "complete";
      options.onProgress?.({ type: "progress", stage });
      return result;
    } finally {
      scope.close();
    }
  }

  async close() {
    await this.bridge?.close();
    this.bridge = null;
  }
}

module.exports = {
  PrivateConversationClient,
  conversationPayload,
  systemMessage,
  userMessage,
};
