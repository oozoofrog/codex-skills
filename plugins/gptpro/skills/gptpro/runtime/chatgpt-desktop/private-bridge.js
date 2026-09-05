"use strict";

const crypto = require("node:crypto");
const { AsyncQueue } = require("./async-queue.js");
const { callExpression, installationExpression } = require("./app-host-http.js");
const { CdpClient } = require("./cdp-client.js");
const { parseSse } = require("./delta-decoder.js");
const { runtimeError } = require("./errors.js");

function headerRecord(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item)]));
}

function signalError(signal, fallback) {
  const reason = signal?.reason;
  return reason && typeof reason === "object" && typeof reason.code === "string" ? reason : fallback;
}

class PrivateDesktopBridge {
  constructor(cdp, bindingName, hookName, environment) {
    this.cdp = cdp;
    this.bindingName = bindingName;
    this.hookName = hookName;
    this.environment = environment;
    this.pending = new Map();
    this.sockets = new Map();
    this.closed = false;
    this.bindingHandler = (params) => this.#binding(params);
    this.closedHandler = (error) => this.#failAll(error);
    cdp.on("binding", this.bindingHandler);
    cdp.on("closed", this.closedHandler);
  }

  static async connect(options = {}) {
    const cdp = await CdpClient.connect(options);
    const suffix = crypto.randomUUID().replaceAll("-", "");
    const bindingName = `__gptpro_bridge_${suffix}`;
    const hookName = `__gptpro_hook_${suffix}`;
    try {
      await cdp.send("Runtime.enable");
      await cdp.send("Runtime.addBinding", { name: bindingName });
      await cdp.evaluate(`(()=>{${installationExpression(bindingName, hookName)};return true;})()`);
      const appHostProbe = await cdp.evaluate(callExpression(hookName, "probe", {}), 5_000);
      if (
        appHostProbe?.ok !== true
        || appHostProbe?.contract !== "app-host-http-v1"
        || appHostProbe?.websocket_supported !== true
      ) {
        throw new Error("app-host HTTP probe failed");
      }
      const environment = await cdp.evaluate(`(async()=>{
        const bridge=window.electronBridge;
        if(typeof bridge?.getSentryInitOptions!=="function") throw new Error("Desktop environment missing");
        const deviceKey="gptpro.chatgpt-conversations.device-id";
        let deviceId;
        try{
          deviceId=window.localStorage.getItem(deviceKey)?.trim();
          if(!deviceId){deviceId=crypto.randomUUID();window.localStorage.setItem(deviceKey,deviceId);}
        }catch{deviceId=crypto.randomUUID();}
        return {
          app_version:bridge.getSentryInitOptions?.().appVersion??null,
          device_check_supported:(await bridge.isDeviceCheckSupported?.())===true,
          desktop_environment_readable:typeof bridge.getSentryInitOptions==="function",
          stream_bridge:typeof MessageChannel==="function"&&typeof window.postMessage==="function"&&typeof globalThis[${JSON.stringify(bindingName)}]==="function"&&typeof window[${JSON.stringify(hookName)}]?.startStream==="function",
          websocket_bridge:typeof WebSocket==="function"&&typeof window[${JSON.stringify(hookName)}]?.openSocket==="function"&&typeof window[${JSON.stringify(hookName)}]?.sendSocket==="function",
          bridge_contract:"app-host-http-v1",
          device_id:deviceId,
          language:navigator.language||"en",
          target_url:location.href
        };
      })()`);
      if (environment?.target_url !== "app://-/index.html") {
        throw runtimeError("TARGET_NOT_FOUND", "The connected renderer identity changed during probe.");
      }
      return new PrivateDesktopBridge(cdp, bindingName, hookName, environment);
    } catch (cause) {
      await cdp.close();
      if (cause?.code) throw cause;
      throw runtimeError("BRIDGE_UNAVAILABLE", "The private Desktop app-host HTTP service is unavailable.", { cause });
    }
  }

  async runtimeCall(method, value, timeoutMs = 10_000, signal = null) {
    if (this.closed) throw runtimeError("BRIDGE_UNAVAILABLE", "The Desktop bridge is closed.");
    return this.cdp.evaluate(callExpression(this.hookName, method, value), timeoutMs, signal);
  }

  request(method, url, options = {}) {
    if (options.signal?.aborted) return Promise.reject(runtimeError("CANCELLED", "The Desktop request was cancelled."));
    const requestId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      let settled = false;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        options.signal?.removeEventListener("abort", abort);
        this.pending.delete(requestId);
        callback(value);
      };
      const cancel = () => void this.runtimeCall("cancel", requestId).catch(() => {});
      const abort = () => {
        cancel();
        finish(reject, signalError(options.signal, runtimeError("CANCELLED", "The Desktop request was cancelled.")));
      };
      const timer = setTimeout(() => {
        cancel();
        finish(reject, runtimeError("TIMEOUT", "Desktop request timed out.", { retryable: true }));
      }, options.timeoutMs ?? 30_000);
      this.pending.set(requestId, {
        kind: "request",
        resolve: (value) => finish(resolve, value),
        reject: (error) => finish(reject, error),
      });
      options.signal?.addEventListener("abort", abort, { once: true });
      void this.runtimeCall("request", {
        requestId,
        method,
        url,
        headers: options.headers,
        body: options.body,
      }, (options.timeoutMs ?? 30_000) + 5_000, options.signal).then((response) => {
        let body = null;
        try { body = response?.bodyText ? JSON.parse(response.bodyText) : null; } catch (cause) {
          finish(reject, runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop request body was invalid JSON.", { cause }));
          return;
        }
        finish(resolve, {
          status: Number(response?.status ?? 500),
          headers: headerRecord(response?.headers),
          body,
        });
      }).catch((cause) => finish(reject, runtimeError("BRIDGE_UNAVAILABLE", "The Desktop app-host HTTP service rejected a request before completion.", { cause })));
    });
  }

  async stream(method, url, options = {}) {
    if (options.signal?.aborted) throw runtimeError("CANCELLED", "The Desktop stream was cancelled.");
    const requestId = crypto.randomUUID();
    const events = new AsyncQueue();
    let terminal = false;
    const cleanup = () => {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", abort);
      this.pending.delete(requestId);
    };
    const fail = (error) => {
      if (terminal) return;
      terminal = true;
      cleanup();
      events.fail(error);
    };
    const complete = () => {
      if (terminal) return;
      terminal = true;
      cleanup();
      events.end();
    };
    const cancel = async (error = runtimeError("CANCELLED", "The Desktop stream was cancelled.", { submissionState: "ambiguous" })) => {
      if (terminal) return;
      fail(error);
      await this.runtimeCall("cancel", requestId).catch(() => {});
    };
    const abort = () => cancel(signalError(
      options.signal,
      runtimeError("CANCELLED", "The Desktop stream was cancelled.", { submissionState: "ambiguous" }),
    ));
    const timer = setTimeout(
      () => cancel(runtimeError("TIMEOUT", "The Desktop conversation stream timed out.", { submissionState: "ambiguous" })),
      options.timeoutMs ?? 600_000,
    );
    const pending = {
      kind: "stream",
      events,
      fail,
      complete,
      sse: "",
      format: options.format ?? "sse",
      receivedChunks: 0,
    };
    this.pending.set(requestId, pending);
    options.signal?.addEventListener("abort", abort, { once: true });
    try {
      await this.runtimeCall("startStream", {
        requestId,
        method,
        url,
        headers: options.headers,
        body: options.body,
      }, (options.timeoutMs ?? 600_000) + 5_000, options.signal);
    } catch (cause) {
      const error = cause?.code
        ? cause
        : runtimeError("SUBMISSION_AMBIGUOUS", "The conversation dispatch result is ambiguous; it will not be resent automatically.", { cause, submissionState: "ambiguous" });
      fail(error);
      throw error;
    }
    return {
      requestId,
      events,
      cancel,
      get receivedChunks() { return pending.receivedChunks; },
    };
  }

  async openWebSocket(value, options = {}) {
    let url;
    try { url = new URL(value); } catch (cause) {
      throw runtimeError("STREAM_HANDOFF_URL_INVALID", "The Desktop handoff URL is invalid.", { cause, submissionState: "ambiguous" });
    }
    if (url.protocol !== "wss:" || url.hostname !== "ws.chatgpt.com" || url.username || url.password) {
      throw runtimeError("STREAM_HANDOFF_URL_INVALID", "The Desktop handoff requires the credential-free wss://ws.chatgpt.com origin.", { submissionState: "ambiguous" });
    }
    if (options.signal?.aborted) throw signalError(options.signal, runtimeError("CANCELLED", "The Desktop handoff was cancelled.", { submissionState: "ambiguous" }));

    const socketId = crypto.randomUUID();
    const events = new AsyncQueue();
    let opened = false;
    let terminal = false;
    let resolveOpen;
    let rejectOpen;
    const openedPromise = new Promise((resolve, reject) => { resolveOpen = resolve; rejectOpen = reject; });
    const cleanup = () => {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", abort);
      this.sockets.delete(socketId);
    };
    const closeRemote = () => void this.runtimeCall("closeSocket", socketId).catch(() => {});
    const fail = (error) => {
      if (terminal) return;
      terminal = true;
      cleanup();
      if (!opened) rejectOpen(error);
      events.fail(error);
      closeRemote();
    };
    const end = (remote = true) => {
      if (terminal) return;
      terminal = true;
      cleanup();
      if (!opened) rejectOpen(runtimeError("STREAM_INTERRUPTED", "The Desktop handoff closed before connecting.", { submissionState: "ambiguous" }));
      events.end();
      if (remote) closeRemote();
    };
    const abort = () => fail(signalError(
      options.signal,
      runtimeError("CANCELLED", "The Desktop handoff was cancelled.", { submissionState: "ambiguous" }),
    ));
    const timer = setTimeout(
      () => fail(runtimeError("STREAM_HANDOFF_CONNECT_TIMEOUT", "The Desktop handoff WebSocket did not connect in time.", { submissionState: "ambiguous" })),
      options.connectTimeoutMs ?? 5_000,
    );
    this.sockets.set(socketId, {
      receive: (raw) => {
        if (raw.type === "gptpro-ws-open") {
          if (opened || terminal) return;
          opened = true;
          clearTimeout(timer);
          resolveOpen();
        } else if (raw.type === "gptpro-ws-message" && opened && typeof raw.data === "string") {
          events.push(raw.data);
        } else if (raw.type === "gptpro-ws-error") {
          fail(runtimeError("STREAM_INTERRUPTED", "The Desktop handoff WebSocket failed.", { submissionState: "ambiguous" }));
        } else if (raw.type === "gptpro-ws-close") {
          if (opened) events.push({ type: "close", code: Number(raw.code) || null });
          end(false);
        }
      },
      fail,
      end,
    });
    options.signal?.addEventListener("abort", abort, { once: true });
    try {
      await this.runtimeCall("openSocket", { socketId, url: url.href }, (options.connectTimeoutMs ?? 5_000) + 5_000, options.signal);
      await openedPromise;
    } catch (cause) {
      const error = cause?.code
        ? cause
        : runtimeError("STREAM_HANDOFF_CONNECT_FAILED", "The Desktop handoff WebSocket could not be opened.", { cause, submissionState: "ambiguous" });
      fail(error);
      throw error;
    }
    return {
      events,
      send: async (data) => {
        if (terminal || typeof data !== "string") {
          throw runtimeError("STREAM_INTERRUPTED", "The Desktop handoff WebSocket is not writable.", { submissionState: "ambiguous" });
        }
        await this.runtimeCall("sendSocket", { socketId, data }, 5_000, options.signal);
      },
      close: async () => end(true),
    };
  }

  async close() {
    if (this.closed) return;
    this.closed = true;
    this.#failAll(runtimeError("CANCELLED", "The Desktop bridge session closed."));
    for (const socket of this.sockets.values()) socket.fail(runtimeError("CANCELLED", "The Desktop bridge session closed.", { submissionState: "ambiguous" }));
    this.cdp.off("binding", this.bindingHandler);
    this.cdp.off("closed", this.closedHandler);
    try {
      await this.cdp.evaluate(`(async()=>{try{await window[${JSON.stringify(this.hookName)}]?.close?.();}catch{}delete window[${JSON.stringify(this.hookName)}];})()`);
      await this.cdp.send("Runtime.removeBinding", { name: this.bindingName });
    } catch {}
    await this.cdp.close();
  }

  #binding(params) {
    if (params?.name !== this.bindingName || typeof params.payload !== "string") return;
    let raw;
    try { raw = JSON.parse(params.payload); } catch { return; }
    if (raw?.marker === "gptpro-app-host-http-v1") {
      if (typeof raw.type === "string" && raw.type.startsWith("gptpro-ws-")) {
        this.sockets.get(raw.socketId)?.receive(raw);
        return;
      }
      const pending = this.pending.get(raw.requestId);
      if (!pending || pending.kind !== "stream") return;
      if (raw.type === "gptpro-http-response") {
        pending.events.push({ type: "fetch-stream-response", status: Number(raw.status), headers: headerRecord(raw.headers) });
      } else if (raw.type === "gptpro-http-chunk" && typeof raw.data === "string") {
        pending.receivedChunks += 1;
        this.#streamChunk(pending, raw.data, false);
      } else if (raw.type === "gptpro-http-error") {
        pending.fail(runtimeError("SUBMISSION_AMBIGUOUS", "The Desktop app-host response failed after dispatch; it will not be resent.", { submissionState: "ambiguous" }));
      } else if (raw.type === "gptpro-http-complete") {
        this.#streamChunk(pending, "", true);
        pending.events.push({ type: "fetch-stream-complete" });
        pending.complete();
      }
      return;
    }
  }

  #streamChunk(pending, chunk, final) {
    if (pending.format === "discard") return;
    pending.sse += chunk;
    if (pending.format === "ndjson") {
      const lines = pending.sse.split(/\r?\n/);
      pending.sse = final ? "" : lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try { pending.events.push({ type: "fetch-stream-event", data: JSON.parse(line) }); } catch {
          pending.fail(runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop NDJSON stream was invalid.", { submissionState: "ambiguous" }));
          return;
        }
      }
      return;
    }
    const normalized = pending.sse.replaceAll("\r\n", "\n");
    const boundary = normalized.lastIndexOf("\n\n");
    if (boundary < 0 && !final) return;
    const complete = final ? normalized : normalized.slice(0, boundary + 2);
    pending.sse = final ? "" : normalized.slice(boundary + 2);
    try {
      for (const event of parseSse(complete)) pending.events.push({ type: "fetch-stream-event", ...event });
    } catch (error) {
      pending.fail(error);
    }
  }

  #failAll(error) {
    for (const item of this.pending.values()) item.kind === "stream" ? item.fail(error) : item.reject(error);
  }
}

module.exports = { PrivateDesktopBridge, headerRecord };
