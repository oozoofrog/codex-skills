"use strict";

const crypto = require("node:crypto");
const { AsyncQueue } = require("./async-queue");
const { rendererRelaySource } = require("./chunked-message");
const { DEFAULT_TARGET_URL } = require("./cdp-client");
const { DesktopRuntimeError } = require("./errors");

const BINDING_NAME = "__gptproDesktopMessage";
const RESPONSE_TYPES = Object.freeze([
  "fetch-response", "fetch-upload-progress", "fetch-stream-response",
  "fetch-stream-event", "fetch-stream-error", "fetch-stream-complete",
]);
const BASE_REQUEST_HEADERS = Object.freeze({
  "OAI-Language": "en",
  "X-OpenAI-Attach-Auth": "1",
  "X-OpenAI-Attach-Desktop-Surface": "1",
  "X-OpenAI-Attach-Integrity-State": "1",
});
const DEVICE_CHECK_HEADERS = Object.freeze({
  "X-OpenAI-Attach-DeviceCheck-Token": "1",
});

function parseBody(message) {
  if (typeof message.bodyJsonString !== "string") return message.body ?? null;
  try { return JSON.parse(message.bodyJsonString); }
  catch { throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Desktop bridge returned invalid JSON"); }
}

class DesktopBridge {
  constructor(cdp, { timeoutMs = 120000 } = {}) {
    this.cdp = cdp;
    this.timeoutMs = timeoutMs;
    this.pending = new Map();
    this.unsubscribe = null;
  }

  async initialize() {
    await this.cdp.send("Runtime.addBinding", { name: BINDING_NAME });
    this.unsubscribe = this.cdp.onEvent((event) => {
      if (event.method !== "Runtime.bindingCalled" || event.params?.name !== BINDING_NAME) return;
      this._receiveBinding(event.params.payload).catch((error) => this._failAll(error));
    });
    await this.cdp.evaluate(rendererRelaySource(BINDING_NAME, RESPONSE_TYPES));
    return this;
  }

  async capabilities() {
    const expression = `(() => {
      const bridge = window.electronBridge;
      if (!bridge) return { desktop_bridge: false, device_check_supported: false, chunked_message_supported: false, desktop_environment_readable: false, app_version: null };
      let appVersion = null;
      try {
        const options = typeof bridge.getSentryInitOptions === "function" ? bridge.getSentryInitOptions() : null;
        if (options && typeof options.appVersion === "string") appVersion = options.appVersion;
      } catch (_) {}
      let deviceCheck = false;
      try { deviceCheck = bridge.isDeviceCheckSupported() === true; } catch (_) {}
      return {
        desktop_bridge: typeof bridge.sendMessageFromView === "function",
        device_check_supported: deviceCheck,
        chunked_message_supported: typeof bridge.acknowledgeChunkedMessage === "function",
        desktop_environment_readable: appVersion !== null,
        app_version: appVersion
      };
    })()`;
    const result = await this.cdp.evaluate(expression);
    if (!result?.desktop_bridge) throw new DesktopRuntimeError("BRIDGE_UNAVAILABLE", "ChatGPT Desktop renderer bridge is unavailable");
    if (!result.device_check_supported) throw new DesktopRuntimeError("DEVICE_CHECK_UNAVAILABLE", "ChatGPT Desktop DeviceCheck capability is unavailable");
    if (!result.chunked_message_supported) throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", "ChatGPT Desktop chunked-message capability is unavailable");
    if (!result.desktop_environment_readable) throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", "ChatGPT Desktop app version capability is unavailable");
    return result;
  }

  async _receiveBinding(payload) {
    let message;
    try { message = JSON.parse(payload); }
    catch { throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Desktop bridge emitted invalid JSON"); }
    this._route(message);
  }

  _route(message) {
    if (!message || typeof message !== "object" || typeof message.requestId !== "string") return;
    const pending = this.pending.get(message.requestId);
    if (!pending) return;
    if (pending.kind === "request") {
      if (message.type === "fetch-response") {
        this.pending.delete(message.requestId);
        clearTimeout(pending.timer);
        pending.cleanup();
        this._deactivateRequest(message.requestId);
        if (message.responseType === "success") pending.resolve({ status: message.status, body: parseBody(message) });
        else pending.reject(new DesktopRuntimeError(pending.errorCode, `Desktop request failed with HTTP ${message.status ?? "unknown"}`));
      }
      return;
    }
    if (message.type === "fetch-stream-response") {
      pending.status = message.status;
      if (!Number.isInteger(message.status) || message.status < 200 || message.status >= 300) {
        this._finishStream(message.requestId);
        pending.queue.fail(new DesktopRuntimeError("CONVERSATION_REJECTED", `Desktop conversation was rejected with HTTP ${message.status ?? "unknown"}`));
      }
    } else if (message.type === "fetch-stream-event") {
      pending.queue.push({ event: message.event || null, data: message.data });
    } else if (message.type === "fetch-stream-error") {
      this._finishStream(message.requestId);
      pending.queue.fail(new DesktopRuntimeError("STREAM_INTERRUPTED", "Desktop conversation stream ended ambiguously"));
    } else if (message.type === "fetch-stream-complete") {
      this._finishStream(message.requestId);
      pending.queue.close();
    }
  }

  _finishStream(requestId) {
    const pending = this.pending.get(requestId);
    if (!pending) return;
    this.pending.delete(requestId);
    clearTimeout(pending.timer);
    pending.cleanup();
    this._deactivateRequest(requestId);
  }

  _failAll(error) {
    for (const [requestId, pending] of this.pending) {
      this.pending.delete(requestId);
      clearTimeout(pending.timer);
      pending.cleanup();
      this._deactivateRequest(requestId);
      if (pending.kind === "stream") pending.queue.fail(error);
      else pending.reject(error);
    }
  }

  async _send(message) {
    const encoded = JSON.stringify(JSON.stringify(message));
    const expression = `(async () => {
      if (window.location.href !== ${JSON.stringify(DEFAULT_TARGET_URL)}) return { ok: false, target_mismatch: true };
      const bridge = window.electronBridge;
      if (!bridge || typeof bridge.sendMessageFromView !== "function") throw new Error("bridge unavailable");
      const message = JSON.parse(${encoded});
      if ((message.type === "fetch" || message.type === "fetch-stream") && typeof message.requestId === "string") {
        window.__gptproDesktopRequestIds.add(message.requestId);
        try {
          const desktopDeviceId = window.localStorage.getItem("codex.chatgpt-conversations.device-id");
          if (typeof desktopDeviceId === "string" && desktopDeviceId) message.headers["oai-did"] = desktopDeviceId;
        } catch (_) {}
      }
      await bridge.sendMessageFromView(message);
      return { ok: true };
    })()`;
    try {
      const result = await this.cdp.evaluate(expression);
      if (result?.target_mismatch) throw new DesktopRuntimeError("TARGET_NOT_FOUND", `Connected renderer is not ${DEFAULT_TARGET_URL}`);
    }
    catch (error) {
      if (error instanceof DesktopRuntimeError) throw error;
      throw new DesktopRuntimeError("BRIDGE_UNAVAILABLE", "Unable to send through the ChatGPT Desktop bridge", { cause: error });
    }
  }

  _deactivateRequest(requestId) {
    if (!this.cdp || typeof this.cdp.evaluate !== "function") return;
    const expression = `(() => {
      if (window.__gptproDesktopRequestIds) window.__gptproDesktopRequestIds.delete(${JSON.stringify(requestId)});
      return true;
    })()`;
    this.cdp.evaluate(expression).catch(() => {});
  }

  _lifecycle(requestId, signal, onAbort) {
    let abortListener = null;
    if (signal) {
      if (signal.aborted) throw new DesktopRuntimeError("CANCELLED", "Operation was cancelled");
      abortListener = () => onAbort(signal.reason);
      signal.addEventListener("abort", abortListener, { once: true });
    }
    return () => { if (abortListener) signal.removeEventListener("abort", abortListener); };
  }

  request({ method = "GET", url, headers = {}, body = null, signal, errorCode = "DESKTOP_CAPABILITY_UNAVAILABLE" }) {
    const requestId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const fail = (error) => {
        const pending = this.pending.get(requestId);
        if (!pending) return;
        this.pending.delete(requestId);
        clearTimeout(pending.timer);
        pending.cleanup();
        this._deactivateRequest(requestId);
        this._send({ type: "cancel-fetch", requestId }).catch(() => {});
        reject(error);
      };
      let cleanup;
      try {
        cleanup = this._lifecycle(requestId, signal, (reason) => fail(
          reason instanceof DesktopRuntimeError ? reason : new DesktopRuntimeError("CANCELLED", "Operation was cancelled")
        ));
      } catch (error) { reject(error); return; }
      const timer = setTimeout(() => fail(new DesktopRuntimeError("TIMEOUT", "Desktop request timed out")), this.timeoutMs);
      this.pending.set(requestId, { kind: "request", resolve, reject, timer, cleanup, errorCode });
      this._send({ type: "fetch", requestId, method, url, headers: { ...BASE_REQUEST_HEADERS, ...headers }, body, reportUploadProgress: false })
        .catch(fail);
    });
  }

  async stream({ method = "POST", url, headers = {}, body, signal, errorCode = "CONVERSATION_REJECTED" }) {
    const requestId = crypto.randomUUID();
    const queue = new AsyncQueue();
    const cancel = (error) => {
      const pending = this.pending.get(requestId);
      if (!pending) return;
      this._finishStream(requestId);
      queue.fail(error);
      this._send({ type: "cancel-fetch-stream", requestId }).catch(() => {});
    };
    const cleanup = this._lifecycle(requestId, signal, (reason) => cancel(
      reason instanceof DesktopRuntimeError ? reason : new DesktopRuntimeError("CANCELLED", "Operation was cancelled")
    ));
    const timer = setTimeout(() => cancel(new DesktopRuntimeError("TIMEOUT", "Desktop conversation timed out")), this.timeoutMs);
    this.pending.set(requestId, { kind: "stream", queue, timer, cleanup, errorCode, status: null });
    try {
      await this._send({ type: "fetch-stream", requestId, method, url, headers: { ...BASE_REQUEST_HEADERS, ...headers }, body, format: "sse" });
    } catch (error) {
      cancel(error);
      throw error;
    }
    return queue;
  }

  close() {
    if (this.unsubscribe) this.unsubscribe();
    this._failAll(new DesktopRuntimeError("CANCELLED", "Desktop bridge closed"));
  }
}

module.exports = { BINDING_NAME, BASE_REQUEST_HEADERS, DEVICE_CHECK_HEADERS, DesktopBridge, parseBody };
