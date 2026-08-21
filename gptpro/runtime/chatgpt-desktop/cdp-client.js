"use strict";

const { DesktopRuntimeError } = require("./errors");

const DEFAULT_ENDPOINT = "http://127.0.0.1:9222";
const DEFAULT_TARGET_URL = "app://-/index.html";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

function abortError(signal) {
  return signal?.reason instanceof DesktopRuntimeError ? signal.reason :
    new DesktopRuntimeError("CANCELLED", "Operation was cancelled");
}

function validateEndpoint(raw = DEFAULT_ENDPOINT) {
  let url;
  try { url = new URL(raw); }
  catch { throw new DesktopRuntimeError("CDP_ENDPOINT_REJECTED", "CDP endpoint must be a valid URL"); }
  if (!new Set(["http:", "https:"]).has(url.protocol)) {
    throw new DesktopRuntimeError("CDP_ENDPOINT_REJECTED", "CDP discovery requires HTTP or HTTPS");
  }
  if (url.username || url.password) {
    throw new DesktopRuntimeError("CDP_ENDPOINT_REJECTED", "CDP endpoint credentials are not allowed");
  }
  if (!LOOPBACK_HOSTS.has(url.hostname.toLowerCase())) {
    throw new DesktopRuntimeError("CDP_ENDPOINT_REJECTED", "Phase 1 permits loopback CDP endpoints only");
  }
  if ((url.pathname && url.pathname !== "/") || url.search || url.hash) {
    throw new DesktopRuntimeError("CDP_ENDPOINT_REJECTED", "CDP endpoint must be a loopback origin without path, query, or fragment");
  }
  url.pathname = "/";
  return url;
}

function validateWebSocketUrl(raw) {
  let url;
  try { url = new URL(raw); }
  catch { throw new DesktopRuntimeError("CDP_ENDPOINT_REJECTED", "CDP target returned an invalid WebSocket URL"); }
  if (!new Set(["ws:", "wss:"]).has(url.protocol) || url.username || url.password ||
      !LOOPBACK_HOSTS.has(url.hostname.toLowerCase())) {
    throw new DesktopRuntimeError("CDP_ENDPOINT_REJECTED", "CDP target WebSocket must remain on loopback");
  }
  return url.toString();
}

function defaultWebSocketFactory(url) {
  if (typeof globalThis.WebSocket !== "function") {
    throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", "ChatGPT Desktop CDP requires Node.js 22 or newer with built-in WebSocket support");
  }
  return new globalThis.WebSocket(url);
}

function selectExactTarget(targets, targetUrl = DEFAULT_TARGET_URL) {
  if (!Array.isArray(targets)) throw new DesktopRuntimeError("CDP_UNAVAILABLE", "CDP target listing is not an array");
  const matches = targets.filter((target) => target && target.type === "page" && target.url === targetUrl);
  if (matches.length !== 1) {
    throw new DesktopRuntimeError("TARGET_NOT_FOUND", `Expected exactly one ChatGPT renderer target at ${targetUrl}`);
  }
  if (typeof matches[0].webSocketDebuggerUrl !== "string") {
    throw new DesktopRuntimeError("TARGET_NOT_FOUND", "ChatGPT renderer target has no debugger WebSocket");
  }
  return matches[0];
}

async function discoverTarget({ endpoint = DEFAULT_ENDPOINT, targetUrl = DEFAULT_TARGET_URL, fetchImpl = globalThis.fetch, signal } = {}) {
  const base = validateEndpoint(endpoint);
  const listingUrl = new URL("/json", base);
  let response;
  try {
    const timeoutSignal = AbortSignal.timeout(5000);
    const requestSignal = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;
    response = await fetchImpl(listingUrl, { method: "GET", redirect: "error", signal: requestSignal });
  } catch (error) {
    if (signal?.aborted) throw abortError(signal);
    throw new DesktopRuntimeError("CDP_UNAVAILABLE", "ChatGPT Desktop CDP endpoint is unavailable", { cause: error });
  }
  if (!response.ok) throw new DesktopRuntimeError("CDP_UNAVAILABLE", `CDP discovery failed with HTTP ${response.status}`);
  let targets;
  try { targets = await response.json(); }
  catch (error) { throw new DesktopRuntimeError("CDP_UNAVAILABLE", "CDP target listing is not valid JSON", { cause: error }); }
  const target = selectExactTarget(targets, targetUrl);
  return { endpoint: base.origin, target, webSocketUrl: validateWebSocketUrl(target.webSocketDebuggerUrl) };
}

class CdpClient {
  constructor(webSocketUrl, { webSocketFactory = defaultWebSocketFactory, commandTimeoutMs = 10000 } = {}) {
    this.webSocketUrl = validateWebSocketUrl(webSocketUrl);
    this.webSocketFactory = webSocketFactory;
    this.commandTimeoutMs = commandTimeoutMs;
    this.socket = null;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
  }

  async connect(signal) {
    if (signal?.aborted) throw abortError(signal);
    let socket;
    try { socket = this.webSocketFactory(this.webSocketUrl); }
    catch (error) {
      if (error instanceof DesktopRuntimeError) throw error;
      throw new DesktopRuntimeError("CDP_UNAVAILABLE", "Unable to create a CDP WebSocket", { cause: error });
    }
    this.socket = socket;
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { cleanup(); socket.close(); reject(new DesktopRuntimeError("TIMEOUT", "CDP WebSocket connection timed out")); }, this.commandTimeoutMs);
      const onOpen = () => { cleanup(); resolve(); };
      const onError = () => { cleanup(); reject(new DesktopRuntimeError("CDP_UNAVAILABLE", "Unable to open CDP WebSocket")); };
      const onAbort = () => { cleanup(); socket.close(); reject(abortError(signal)); };
      const cleanup = () => {
        clearTimeout(timer);
        socket.removeEventListener("open", onOpen);
        socket.removeEventListener("error", onError);
        if (signal) signal.removeEventListener("abort", onAbort);
      };
      socket.addEventListener("open", onOpen, { once: true });
      socket.addEventListener("error", onError, { once: true });
      if (signal) signal.addEventListener("abort", onAbort, { once: true });
    });
    socket.addEventListener("message", (event) => this._message(event.data));
    socket.addEventListener("close", () => this._closePending());
    await this.send("Runtime.enable");
    if (signal?.aborted) throw abortError(signal);
    return this;
  }

  _message(raw) {
    let message;
    try { message = JSON.parse(typeof raw === "string" ? raw : String(raw)); }
    catch { return; }
    if (message.id) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", "CDP command failed"));
      else pending.resolve(message.result || {});
      return;
    }
    for (const listener of this.listeners) listener(message);
  }

  _closePending() {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(new DesktopRuntimeError("STREAM_INTERRUPTED", "CDP WebSocket closed"));
    }
    this.pending.clear();
  }

  onEvent(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }

  send(method, params = {}) {
    if (!this.socket || this.socket.readyState !== 1) {
      return Promise.reject(new DesktopRuntimeError("CDP_UNAVAILABLE", "CDP WebSocket is not open"));
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new DesktopRuntimeError("TIMEOUT", `CDP command timed out: ${method}`));
      }, this.commandTimeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression, { awaitPromise = true, returnByValue = true } = {}) {
    const result = await this.send("Runtime.evaluate", { expression, awaitPromise, returnByValue, userGesture: false });
    if (result.exceptionDetails) throw new DesktopRuntimeError("DESKTOP_CAPABILITY_UNAVAILABLE", "ChatGPT renderer evaluation failed");
    return result.result ? result.result.value : undefined;
  }

  close() { if (this.socket) this.socket.close(); }
}

module.exports = { DEFAULT_ENDPOINT, DEFAULT_TARGET_URL, validateEndpoint, validateWebSocketUrl, defaultWebSocketFactory, selectExactTarget, discoverTarget, CdpClient };
