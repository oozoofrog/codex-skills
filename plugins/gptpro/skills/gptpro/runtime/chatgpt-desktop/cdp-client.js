"use strict";

const { EventEmitter } = require("node:events");
const { execFile } = require("node:child_process");
const os = require("node:os");
const path = require("node:path");
const { promisify } = require("node:util");
const { runtimeError } = require("./errors.js");

const execFileAsync = promisify(execFile);
const RUNNER_PORT = 9223;
const DEFAULT_ENDPOINT = `http://127.0.0.1:${RUNNER_PORT}`;
const RUNNER_PROFILE = path.join(os.homedir(), "Library", "Application Support", "gptpro", "runner", "v1", "profile");
const TARGET_URL = "app://-/index.html";

function validateEndpoint(input = DEFAULT_ENDPOINT) {
  let endpoint;
  try {
    endpoint = new URL(input);
  } catch (cause) {
    throw runtimeError("CDP_ENDPOINT_REJECTED", "The CDP endpoint is not a valid URL.", { cause });
  }
  if (endpoint.protocol !== "http:" || endpoint.username || endpoint.password || endpoint.pathname !== "/" || endpoint.search || endpoint.hash) {
    throw runtimeError("CDP_ENDPOINT_REJECTED", "Phase 1 accepts only a credential-free loopback HTTP CDP endpoint.");
  }
  const host = endpoint.hostname.toLowerCase();
  if (!["127.0.0.1", "localhost", "[::1]", "::1"].includes(host)) {
    throw runtimeError("CDP_ENDPOINT_REJECTED", "Remote CDP endpoints are prohibited.");
  }
  const port = endpoint.port ? Number(endpoint.port) : 80;
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw runtimeError("CDP_ENDPOINT_REJECTED", "The CDP endpoint port is invalid.");
  }
  endpoint.pathname = "/";
  return endpoint;
}

function selectRendererTarget(targets) {
  const matches = Array.isArray(targets)
    ? targets.filter((item) => item?.type === "page" && item?.url === TARGET_URL && typeof item?.webSocketDebuggerUrl === "string")
    : [];
  if (matches.length !== 1) {
    throw runtimeError("TARGET_NOT_FOUND", "Exactly one ChatGPT renderer target at app://-/index.html is required.");
  }
  return matches[0];
}

async function defaultListenerInspector(endpoint) {
  if (process.platform !== "darwin") {
    throw runtimeError("PLATFORM_UNSUPPORTED", "The Electron runtime currently supports macOS only.");
  }
  const port = endpoint.port || "80";
  let stdout;
  try {
    ({ stdout } = await execFileAsync("/usr/sbin/lsof", ["-nP", "-a", `-iTCP:${port}`, "-sTCP:LISTEN", "-Fpucn"], { timeout: 5_000, maxBuffer: 64 * 1024 }));
  } catch (cause) {
    throw listenerInspectionError(cause);
  }
  const groups = parseListenerOutput(stdout);
  if (!groups.length || groups.some((item) => !Number.isInteger(item.pid))) {
    throw runtimeError("CDP_LISTENER_UNVERIFIED", "The CDP port ownership could not be verified.");
  }
  let ps;
  try {
    ({ stdout: ps } = await execFileAsync("/bin/ps", ["-axo", "pid=,ppid=,uid=,command="], { timeout: 5_000, maxBuffer: 4 * 1024 * 1024 }));
  } catch (cause) {
    throw listenerCommandError(cause);
  }
  return verifyListenerGroupIdentity(groups, ps, process.getuid(), {
    runnerProfile: Number(endpoint.port || 80) === RUNNER_PORT ? RUNNER_PROFILE : null,
    runnerPort: Number(endpoint.port || 80) === RUNNER_PORT ? RUNNER_PORT : null,
  });
}

function listenerCommandError(cause) {
  return runtimeError("CDP_LISTENER_UNVERIFIED", "The CDP listener command could not be verified.", {
    cause,
    retryable: true,
    recovery: "Run desktop-doctor, then retry only if the package still has no submission record.",
  });
}

function listenerInspectionError(cause) {
  const partial = parseListenerOutput(cause?.stdout ?? "");
  if (Number(cause?.code) === 1 && partial.length === 0) {
    return runtimeError(
      "CDP_UNAVAILABLE",
      "No loopback CDP listener is available at the configured endpoint.",
      { cause, retryable: true },
    );
  }
  return runtimeError("CDP_LISTENER_UNVERIFIED", "The loopback CDP listener process could not be verified.", { cause });
}

function parseListenerOutput(stdout) {
  const groups = [];
  let current = null;
  for (const line of String(stdout).split(/\r?\n/)) {
    if (line.startsWith("p")) {
      current = { pid: Number(line.slice(1)), uid: null, command: "", names: [] };
      groups.push(current);
    } else if (current && line.startsWith("u")) current.uid = Number(line.slice(1));
    else if (current && line.startsWith("c")) current.command = line.slice(1);
    else if (current && line.startsWith("n")) current.names.push(line.slice(1));
  }
  return groups;
}

function verifyListenerIdentity(listener, psOutput, expectedUid) {
  const match = String(psOutput).trim().match(/^(\d+)\s+(.+)$/s);
  const expectedExecutable = "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT";
  const names = Array.isArray(listener?.names) ? listener.names : [];
  const onlyLoopback = names.length > 0 && names.every((name) => (
    /^127\.0\.0\.1:\d+$/.test(name)
    || /^localhost:\d+$/.test(name)
    || /^\[::1\]:\d+$/.test(name)
  ));
  if (
    !listener
    || !Number.isInteger(listener.pid)
    || listener.uid !== expectedUid
    || !match
    || Number(match[1]) !== expectedUid
    || !match[2].startsWith(expectedExecutable)
    || !onlyLoopback
  ) {
    throw runtimeError(
      "CDP_LISTENER_UNVERIFIED",
      "The CDP listener is not a loopback-only current-user /Applications/ChatGPT.app process.",
    );
  }
  return { pid: listener.pid, owner_uid: Number(match[1]), executable: expectedExecutable, loopback_only: true };
}

function parseProcessTable(stdout) {
  const table = new Map();
  for (const line of String(stdout).split(/\r?\n/)) {
    const match = line.trim().match(/^(\d+)\s+(\d+)\s+(\d+)\s+(.+)$/s);
    if (!match) continue;
    const value = {
      pid: Number(match[1]),
      ppid: Number(match[2]),
      uid: Number(match[3]),
      command: match[4],
    };
    table.set(value.pid, value);
  }
  return table;
}

function isDescendant(pid, ancestorPid, table) {
  const seen = new Set();
  let current = pid;
  while (Number.isInteger(current) && current > 0 && !seen.has(current)) {
    if (current === ancestorPid) return true;
    seen.add(current);
    current = table.get(current)?.ppid;
  }
  return false;
}

function verifyListenerGroupIdentity(listeners, psOutput, expectedUid, options = {}) {
  const expectedExecutable = "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT";
  const table = parseProcessTable(psOutput);
  const validLoopback = (listener) => (
    Array.isArray(listener?.names)
    && listener.names.length > 0
    && listener.names.every((name) => (
      /^127\.0\.0\.1:\d+$/.test(name)
      || /^localhost:\d+$/.test(name)
      || /^\[::1\]:\d+$/.test(name)
    ))
  );
  const primary = listeners.filter((listener) => {
    const processValue = table.get(listener?.pid);
    const runnerArgumentsMatch = !options.runnerProfile || (
      processValue?.command.includes(`--user-data-dir=${options.runnerProfile}`)
      && processValue?.command.includes(`--remote-debugging-port=${options.runnerPort}`)
    );
    return (
      processValue
      && listener.uid === expectedUid
      && processValue.uid === expectedUid
      && (processValue.command === expectedExecutable || processValue.command.startsWith(expectedExecutable + " "))
      && runnerArgumentsMatch
      && validLoopback(listener)
    );
  });
  if (primary.length !== 1) {
    throw runtimeError(
      "CDP_LISTENER_UNVERIFIED",
      "The CDP listener does not have exactly one verified current-user ChatGPT owner.",
    );
  }
  const root = primary[0];
  for (const listener of listeners) {
    const processValue = table.get(listener?.pid);
    if (
      !processValue
      || listener.uid !== expectedUid
      || processValue.uid !== expectedUid
      || !validLoopback(listener)
      || !isDescendant(listener.pid, root.pid, table)
    ) {
      throw runtimeError(
        "CDP_LISTENER_UNVERIFIED",
        "An additional CDP listener holder is not a verified descendant of the ChatGPT process.",
      );
    }
  }
  return {
    pid: root.pid,
    owner_uid: expectedUid,
    executable: expectedExecutable,
    loopback_only: true,
    inherited_listener_holders: listeners.length - 1,
    isolated_runner: Boolean(options.runnerProfile),
  };
}

function assertDebuggerUrl(value, endpoint) {
  let url;
  try {
    url = new URL(value);
  } catch (cause) {
    throw runtimeError("CDP_ENDPOINT_REJECTED", "The renderer supplied an invalid debugger WebSocket URL.", { cause });
  }
  if (url.protocol !== "ws:" || url.username || url.password) {
    throw runtimeError("CDP_ENDPOINT_REJECTED", "The renderer debugger URL is unsafe.");
  }
  const endpointHost = endpoint.hostname.toLowerCase();
  const socketHost = url.hostname.toLowerCase();
  if (!["127.0.0.1", "localhost", "[::1]", "::1"].includes(socketHost) || (url.port && Number(url.port) !== Number(endpoint.port || 80))) {
    throw runtimeError("CDP_ENDPOINT_REJECTED", "The renderer debugger URL escaped the approved loopback listener.");
  }
  if (endpointHost === "localhost" && !["localhost", "127.0.0.1", "[::1]", "::1"].includes(socketHost)) {
    throw runtimeError("CDP_ENDPOINT_REJECTED", "The renderer debugger host is not loopback.");
  }
  return url.href;
}

class CdpClient extends EventEmitter {
  constructor(socket) {
    super();
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.closed = false;
    socket.addEventListener("message", (event) => this.#message(String(event.data)));
    socket.addEventListener("close", () => this.#close(runtimeError("CDP_UNAVAILABLE", "The CDP WebSocket closed.")));
    socket.addEventListener("error", () => this.#close(runtimeError("CDP_UNAVAILABLE", "The CDP WebSocket failed.")));
  }

  static async connect(options = {}) {
    const endpoint = validateEndpoint(options.endpoint ?? DEFAULT_ENDPOINT);
    const inspect = options.listenerInspector ?? defaultListenerInspector;
    const listener = await inspect(endpoint);
    const fetchImpl = options.fetchImpl ?? globalThis.fetch;
    let response;
    try {
      response = await fetchImpl(new URL("json", endpoint), { signal: AbortSignal.timeout(options.discoveryTimeoutMs ?? 5_000) });
    } catch (cause) {
      throw runtimeError("CDP_UNAVAILABLE", "The loopback CDP target listing is unavailable.", { cause, retryable: true });
    }
    if (!response.ok) throw runtimeError("CDP_UNAVAILABLE", `The CDP target listing returned HTTP ${response.status}.`);
    let targets;
    try {
      targets = await response.json();
    } catch (cause) {
      throw runtimeError("CDP_UNAVAILABLE", "The CDP target listing is invalid JSON.", { cause });
    }
    const target = selectRendererTarget(targets);
    const debuggerUrl = assertDebuggerUrl(target.webSocketDebuggerUrl, endpoint);
    const WebSocketImpl = options.WebSocketImpl ?? globalThis.WebSocket;
    if (typeof WebSocketImpl !== "function") throw runtimeError("NODE_VERSION_UNSUPPORTED", "Node 22 or newer with built-in WebSocket is required.");
    const socket = new WebSocketImpl(debuggerUrl);
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(runtimeError("CDP_UNAVAILABLE", "The CDP WebSocket connection timed out.")), options.connectTimeoutMs ?? 5_000);
        socket.addEventListener("open", () => { clearTimeout(timer); resolve(); }, { once: true });
        socket.addEventListener("error", () => { clearTimeout(timer); reject(runtimeError("CDP_UNAVAILABLE", "The CDP WebSocket connection failed.")); }, { once: true });
      });
    } catch (error) {
      try { socket.close(); } catch {}
      throw error;
    }
    const client = new CdpClient(socket);
    client.endpoint = endpoint.href.replace(/\/$/, "");
    client.target = { id: target.id ?? null, type: target.type, url: target.url };
    client.listener = listener;
    return client;
  }

  send(method, params = {}, timeoutMs = 10_000, signal = null) {
    if (this.closed) return Promise.reject(runtimeError("CDP_UNAVAILABLE", "The CDP session is closed."));
    if (signal?.aborted) {
      return Promise.reject(typeof signal.reason?.code === "string" ? signal.reason : runtimeError("CANCELLED", `CDP command ${method} was cancelled.`));
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const finish = (callback, value) => {
        const pending = this.pending.get(id);
        if (!pending) return;
        this.pending.delete(id);
        clearTimeout(pending.timer);
        signal?.removeEventListener("abort", pending.abort);
        callback(value);
      };
      const abort = () => finish(
        reject,
        typeof signal.reason?.code === "string" ? signal.reason : runtimeError("CANCELLED", `CDP command ${method} was cancelled.`),
      );
      const timer = setTimeout(() => {
        finish(reject, runtimeError("TIMEOUT", `CDP command ${method} timed out.`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (value) => finish(resolve, value),
        reject: (error) => finish(reject, error),
        timer,
        abort,
      });
      signal?.addEventListener("abort", abort, { once: true });
      try {
        this.socket.send(JSON.stringify({ id, method, params }));
      } catch (cause) {
        finish(reject, runtimeError("CDP_UNAVAILABLE", `CDP command ${method} could not be sent.`, { cause }));
      }
    });
  }

  async evaluate(expression, timeoutMs = 10_000, signal = null) {
    const result = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, timeoutMs, signal);
    if (result?.exceptionDetails) throw runtimeError("BRIDGE_UNAVAILABLE", "The ChatGPT renderer rejected a private bridge operation.");
    return result?.result?.value;
  }

  async close() {
    if (this.closed) return;
    this.closed = true;
    try { this.socket.close(); } catch {}
    this.#rejectAll(runtimeError("CANCELLED", "The CDP session was closed."));
  }

  #message(raw) {
    let message;
    try { message = JSON.parse(raw); } catch { return; }
    if (Number.isInteger(message.id)) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      if (message.error) pending.reject(runtimeError("CDP_PROTOCOL_ERROR", "A CDP command failed."));
      else pending.resolve(message.result);
      return;
    }
    if (message.method === "Runtime.bindingCalled") this.emit("binding", message.params);
  }

  #rejectAll(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }

  #close(error) {
    if (this.closed) return;
    this.closed = true;
    this.#rejectAll(error);
    this.emit("closed", error);
  }
}

module.exports = {
  CdpClient,
  DEFAULT_ENDPOINT,
  RUNNER_PORT,
  RUNNER_PROFILE,
  TARGET_URL,
  assertDebuggerUrl,
  defaultListenerInspector,
  listenerCommandError,
  listenerInspectionError,
  parseListenerOutput,
  parseProcessTable,
  selectRendererTarget,
  validateEndpoint,
  verifyListenerGroupIdentity,
  verifyListenerIdentity,
};
