"use strict";

/*
 * Clean-room, minimum MessagePort RPC client for the private ChatGPT Desktop
 * app-host HTTP service. This module intentionally implements only the value
 * kinds and RPC operations required by httpFetch.fetch/cancel and streamed
 * Response bodies. It does not inspect renderer credentials or storage.
 */

function installAppHostHttpRuntime(configuration) {
  const { bindingName, hookName } = configuration;

  function encode(value, depth = 0) {
    if (depth > 128) throw new TypeError("RPC value is too deep.");
    if (value === undefined || value === null || ["boolean", "number", "string"].includes(typeof value)) return value;
    if (typeof value === "bigint") return ["bigint", value.toString()];
    if (value instanceof Uint8Array) return ["bytes", value];
    if (value instanceof ArrayBuffer) return ["bytes", new Uint8Array(value), "ArrayBuffer"];
    if (Array.isArray(value)) return [value.map((item) => encode(item, depth + 1))];
    if (value instanceof Error) return ["error", value.name, value.message, value.stack ?? null];
    if (Object.getPrototypeOf(value) === Object.prototype) {
      const result = {};
      for (const [key, item] of Object.entries(value)) {
        if (["__proto__", "prototype", "constructor"].includes(key)) continue;
        result[key] = encode(item, depth + 1);
      }
      return result;
    }
    throw new TypeError("Unsupported RPC value type.");
  }

  function makeError(value) {
    if (value instanceof Error) return value;
    const error = new Error(typeof value === "string" ? value : "Desktop app-host RPC failed.");
    error.name = "AppHostRpcError";
    return error;
  }

  class PipeBody {
    constructor() {
      const stream = new TransformStream();
      this.readable = stream.readable;
      this.writer = stream.writable.getWriter();
      this.closed = false;
    }

    async write(value) {
      if (this.closed) throw new Error("Response body pipe is already closed.");
      const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
      await this.writer.write(bytes);
    }

    async close() {
      if (this.closed) return;
      this.closed = true;
      await this.writer.close();
    }

    async abort(reason) {
      if (this.closed) return;
      this.closed = true;
      await this.writer.abort(makeError(reason));
    }
  }

  class RpcSession {
    constructor(port) {
      this.port = port;
      this.imports = [null];
      this.exports = [{}];
      this.pending = new Map();
      this.closed = false;
      port.addEventListener("message", (event) => this.receive(event.data));
      port.addEventListener("messageerror", () => this.abort(new Error("MessagePort message error."), false));
      port.start();
    }

    send(value) {
      if (this.closed) throw new Error("Desktop app-host RPC is closed.");
      this.port.postMessage(value);
    }

    call(path, parameters = []) {
      if (!Array.isArray(path) || !path.every((item) => typeof item === "string" || Number.isSafeInteger(item))) {
        return Promise.reject(new TypeError("RPC path is invalid."));
      }
      const id = this.imports.length;
      let resolve;
      let reject;
      const promise = new Promise((success, failure) => { resolve = success; reject = failure; });
      this.imports.push({ resolve, reject });
      this.pending.set(id, { resolve, reject });
      try {
        const encoded = encode(parameters);
        this.send(["push", ["pipeline", 0, path, encoded[0]]]);
        this.send(["pull", id]);
      } catch (error) {
        this.pending.delete(id);
        reject(error);
      }
      return promise;
    }

    decode(value, depth = 0) {
      if (depth > 128) throw new TypeError("RPC value is too deep.");
      if (!Array.isArray(value)) {
        if (value && typeof value === "object") {
          const result = {};
          for (const [key, item] of Object.entries(value)) {
            if (["__proto__", "prototype", "constructor"].includes(key)) continue;
            result[key] = this.decode(item, depth + 1);
          }
          return result;
        }
        return value;
      }
      if (value.length === 1 && Array.isArray(value[0])) return value[0].map((item) => this.decode(item, depth + 1));
      const tag = value[0];
      if (tag === "undefined") return undefined;
      if (tag === "bigint") return BigInt(value[1]);
      if (tag === "bytes") {
        const bytes = value[1];
        if (bytes instanceof Uint8Array) return bytes;
        if (bytes instanceof ArrayBuffer) return new Uint8Array(bytes);
        throw new TypeError("RPC byte payload is invalid.");
      }
      if (tag === "error") {
        const error = new Error(String(value[2] ?? "Desktop app-host RPC failed."));
        error.name = String(value[1] ?? "Error");
        if (typeof value[3] === "string") error.stack = value[3];
        if (value[4] && typeof value[4] === "object") Object.assign(error, this.decode(value[4], depth + 1));
        return error;
      }
      if (tag === "url") return new URL(String(value[1]));
      if (tag === "headers") return value[1];
      if (tag === "readable") {
        const entry = this.exports[value[1]];
        if (!entry || entry.kind !== "pipe" || !entry.body) throw new Error("Response body pipe is unavailable.");
        const readable = entry.body.readable;
        entry.consumed = true;
        return readable;
      }
      if (tag === "response") {
        const body = this.decode(value[1], depth + 1);
        const init = value[2] && typeof value[2] === "object" ? value[2] : {};
        return new Response(body, {
          status: Number(init.status ?? 200),
          statusText: String(init.statusText ?? ""),
          headers: init.headers ?? [],
        });
      }
      throw new TypeError(`Unsupported RPC special value: ${String(tag)}`);
    }

    async evaluate(expression) {
      if (!Array.isArray(expression) || expression[0] !== "pipeline" || !Number.isSafeInteger(expression[1])) {
        throw new TypeError("Unsupported RPC expression.");
      }
      const path = expression[2];
      if (!Array.isArray(path) || !path.every((item) => typeof item === "string" || Number.isSafeInteger(item))) {
        throw new TypeError("RPC expression path is invalid.");
      }
      let target = this.exports[expression[1]];
      if (!target) throw new Error("RPC export is unavailable.");
      let parent = null;
      for (const part of path) {
        if (["__proto__", "prototype", "constructor"].includes(part)) throw new TypeError("Unsafe RPC path.");
        parent = target;
        target = target?.[part];
      }
      if (expression.length === 3) return target;
      if (typeof target !== "function") throw new TypeError("RPC path is not callable.");
      const parameters = this.decode([expression[3]]);
      return target.apply(parent, parameters);
    }

    addExport(result, autoResolve) {
      const id = this.exports.length;
      const entry = { kind: "result", promise: Promise.resolve(result), released: false };
      this.exports.push(entry);
      if (autoResolve) void this.resolveExport(id);
      return id;
    }

    async resolveExport(id) {
      const entry = this.exports[id];
      if (!entry || entry.kind !== "result") throw new Error("RPC result export is unavailable.");
      if (this.closed) return;
      try {
        this.send(["resolve", id, encode(await entry.promise)]);
      } catch (error) {
        if (!this.closed) {
          try { this.send(["reject", id, encode(makeError(error))]); } catch {}
        }
      }
    }

    async receive(message) {
      if (this.closed) return;
      try {
        if (message === null) { this.abort(new Error("Desktop app-host RPC peer closed."), false); return; }
        if (!Array.isArray(message)) throw new TypeError("Desktop app-host RPC message is invalid.");
        const type = message[0];
        if (type === "pipe") {
          const body = new PipeBody();
          this.exports.push({
            kind: "pipe",
            body,
            consumed: false,
            write: (value) => body.write(value),
            close: () => body.close(),
            abort: (reason) => body.abort(reason),
          });
          return;
        }
        if (type === "push" || type === "stream") {
          const result = this.evaluate(message[1]);
          this.addExport(result, type === "stream");
          return;
        }
        if (type === "pull") { await this.resolveExport(message[1]); return; }
        if (type === "resolve" || type === "reject") {
          const id = message[1];
          const pending = this.pending.get(id);
          if (!pending) return;
          this.pending.delete(id);
          const decoded = this.decode(message[2]);
          try { this.send(["release", id, 1]); } catch {}
          if (type === "reject") pending.reject(makeError(decoded));
          else pending.resolve(decoded);
          return;
        }
        if (type === "release") {
          const entry = this.exports[message[1]];
          if (entry) entry.released = true;
          return;
        }
        if (type === "abort") {
          this.abort(makeError(this.decode(message[1])), false);
          return;
        }
        throw new TypeError("Unsupported Desktop app-host RPC message.");
      } catch (error) {
        this.abort(error, true);
      }
    }

    abort(reason, notify = true) {
      if (this.closed) return;
      this.closed = true;
      const error = makeError(reason);
      if (notify) {
        try { this.port.postMessage(["abort", encode(error)]); } catch {}
      }
      try { this.port.close(); } catch {}
      for (const pending of this.pending.values()) pending.reject(error);
      this.pending.clear();
      for (const entry of this.exports) if (entry?.kind === "pipe") void entry.body.abort(error).catch(() => {});
    }
  }

  function headersRecord(headers) {
    const result = {};
    headers.forEach((value, key) => { result[key] = value; });
    return result;
  }

  async function readText(response, emitChunk) {
    if (!response.body) return "";
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let complete = "";
    try {
      while (true) {
        const item = await reader.read();
        if (item.done) break;
        const text = decoder.decode(item.value, { stream: true });
        if (text) {
          complete += text;
          emitChunk?.(text);
        }
      }
      const tail = decoder.decode();
      if (tail) {
        complete += tail;
        emitChunk?.(tail);
      }
      return complete;
    } finally {
      try { reader.releaseLock(); } catch {}
    }
  }

  const previous = window[hookName];
  try { previous?.close?.(); } catch {}
  const channel = new MessageChannel();
  const session = new RpcSession(channel.port1);
  window.postMessage({ type: "connect-app-host", port: channel.port2 }, window.location.origin, [channel.port2]);
  const controllers = new Map();
  const tasks = new Map();
  const sockets = new Map();
  const emit = (value) => {
    try { globalThis[bindingName](JSON.stringify({ marker: "gptpro-app-host-http-v1", ...value })); } catch {}
  };

  async function fetchHttp(requestId, request) {
    return session.call(["services", "httpFetch", "fetch"], [requestId, request, undefined]);
  }

  const runtime = {
    async probe() {
      const requestId = `gptpro-probe-${crypto.randomUUID()}`;
      await session.call(["services", "httpFetch", "cancel"], [requestId]);
      return {
        ok: true,
        contract: "app-host-http-v1",
        websocket_supported: typeof WebSocket === "function",
      };
    },
    async request(request) {
      const requestId = request.requestId;
      const result = await fetchHttp(requestId, request);
      if (!result || !(result.response instanceof Response)) {
        return {
          status: Number(result?.status ?? 500),
          headers: {},
          bodyText: "",
          error: String(result?.error ?? "Desktop HTTP request failed."),
          errorCode: result?.errorCode ?? null,
          responseStatus: result?.responseStatus ?? null,
          errorKind: result?.errorKind ?? null,
        };
      }
      const response = result.response;
      try {
        return {
          status: response.status,
          headers: headersRecord(response.headers),
          bodyText: await readText(response),
          error: null,
        };
      } finally {
        void session.call(["services", "httpFetch", "cancel"], [requestId]).catch(() => {});
      }
    },
    startStream(request) {
      const requestId = request.requestId;
      if (controllers.has(requestId)) throw new Error("Duplicate Desktop stream request ID.");
      const controller = new AbortController();
      controllers.set(requestId, controller);
      const task = (async () => {
        try {
          const result = await fetchHttp(requestId, request);
          if (!result || !(result.response instanceof Response)) {
            const responseStatus = Number(result?.responseStatus);
            if (Number.isInteger(responseStatus) && responseStatus >= 100 && responseStatus <= 599) {
              emit({ type: "gptpro-http-response", requestId, status: responseStatus, headers: {} });
              emit({ type: "gptpro-http-complete", requestId });
            } else {
              emit({ type: "gptpro-http-error", requestId, status: Number(result?.status ?? 500), errorCode: result?.errorCode ?? null, responseStatus: null, errorKind: result?.errorKind ?? null });
            }
            return;
          }
          const response = result.response;
          emit({ type: "gptpro-http-response", requestId, status: response.status, headers: headersRecord(response.headers) });
          await readText(response, (data) => {
            if (!controller.signal.aborted) emit({ type: "gptpro-http-chunk", requestId, data });
          });
          if (!controller.signal.aborted) emit({ type: "gptpro-http-complete", requestId });
        } catch (error) {
          if (!controller.signal.aborted) emit({ type: "gptpro-http-error", requestId, errorCode: null });
        } finally {
          controllers.delete(requestId);
          await session.call(["services", "httpFetch", "cancel"], [requestId]).catch(() => {});
        }
      })();
      tasks.set(requestId, task);
      void task.finally(() => tasks.delete(requestId)).catch(() => {});
      return requestId;
    },
    async cancel(requestId) {
      controllers.get(requestId)?.abort();
      controllers.delete(requestId);
      await session.call(["services", "httpFetch", "cancel"], [requestId]).catch(() => {});
      await tasks.get(requestId)?.catch(() => {});
    },
    openSocket(request) {
      const socketId = request?.socketId;
      if (typeof socketId !== "string" || !socketId || sockets.has(socketId)) {
        throw new Error("Invalid or duplicate Desktop WebSocket ID.");
      }
      const url = new URL(String(request?.url ?? ""));
      if (url.protocol !== "wss:" || url.username || url.password) {
        throw new Error("Only credential-free wss Desktop handoff URLs are accepted.");
      }
      const socket = new WebSocket(url.href);
      sockets.set(socketId, socket);
      socket.addEventListener("open", () => {
        emit({ type: "gptpro-ws-open", socketId });
      });
      socket.addEventListener("message", (event) => {
        if (typeof event.data === "string") emit({ type: "gptpro-ws-message", socketId, data: event.data });
        else emit({ type: "gptpro-ws-error", socketId, errorCode: "NON_TEXT_FRAME" });
      });
      socket.addEventListener("error", () => {
        emit({ type: "gptpro-ws-error", socketId, errorCode: "SOCKET_ERROR" });
      });
      socket.addEventListener("close", (event) => {
        sockets.delete(socketId);
        emit({ type: "gptpro-ws-close", socketId, code: event.code, reason: "" });
      });
      return socketId;
    },
    sendSocket(request) {
      const socket = sockets.get(request?.socketId);
      if (!socket || socket.readyState !== 1) throw new Error("Desktop handoff WebSocket is not open.");
      if (typeof request?.data !== "string") throw new Error("Desktop handoff WebSocket accepts text frames only.");
      socket.send(request.data);
      return true;
    },
    closeSocket(socketId) {
      const socket = sockets.get(socketId);
      sockets.delete(socketId);
      try { socket?.close(); } catch {}
      return true;
    },
    async close() {
      for (const socketId of [...sockets.keys()]) runtime.closeSocket(socketId);
      await Promise.all([...controllers.keys()].map((requestId) => runtime.cancel(requestId)));
      session.abort(new Error("gptpro Desktop session closed."), false);
      if (window[hookName] === runtime) delete window[hookName];
    },
  };
  window[hookName] = runtime;
  return runtime;
}

function installationExpression(bindingName, hookName) {
  return `(${installAppHostHttpRuntime.toString()})(${JSON.stringify({ bindingName, hookName })})`;
}

function callExpression(hookName, method, value) {
  const payload = Buffer.from(JSON.stringify(value), "utf8").toString("base64");
  const parsed = `JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(${JSON.stringify(payload)}),x=>x.charCodeAt(0))))`;
  return `window[${JSON.stringify(hookName)}].${method}(${parsed})`;
}

module.exports = { callExpression, installationExpression, installAppHostHttpRuntime };
