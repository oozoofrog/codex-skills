"use strict";

const { DesktopRuntimeError } = require("./errors");

function clone(value) { return value === undefined ? undefined : structuredClone(value); }

function pathPart(part) {
  if (typeof part === "number" && Number.isSafeInteger(part) && part >= 0) return part;
  const decoded = String(part).replace(/~1/g, "/").replace(/~0/g, "~");
  return /^(?:0|[1-9]\d*)$/.test(decoded) ? Number(decoded) : decoded;
}

function pathParts(path) {
  if (Array.isArray(path)) return path.map(pathPart);
  if (typeof path !== "string" || path === "") return [];
  return (path.startsWith("/") ? path.slice(1) : path).split("/").map(pathPart);
}

function containerFor(nextPart) { return typeof nextPart === "number" ? [] : {}; }

function parentAt(root, parts, create) {
  let current = root;
  for (let index = 0; index < parts.length - 1; index += 1) {
    const part = parts[index];
    if (current == null || typeof current !== "object") throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Delta path crosses a scalar value");
    if (!(part in current)) {
      if (!create) throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Delta path does not exist");
      current[part] = containerFor(parts[index + 1]);
    }
    current = current[part];
  }
  return [current, parts.at(-1)];
}

function appendValue(current, value) {
  if (typeof current === "string") return current + String(value ?? "");
  if (Array.isArray(current)) {
    current.push(...(Array.isArray(value) ? clone(value) : [clone(value)]));
    return current;
  }
  if (current && typeof current === "object" && !Array.isArray(current) &&
      value && typeof value === "object" && !Array.isArray(value)) {
    return Object.assign(current, clone(value));
  }
  return clone(value);
}

function targetAt(root, parts) {
  let current = root;
  for (const part of parts) {
    if (current == null || typeof current !== "object" || !(part in current)) return undefined;
    current = current[part];
  }
  return current;
}

function setAt(root, parts, value) {
  if (!parts.length) return value;
  const base = root == null ? containerFor(parts[0]) : clone(root);
  const [parent, key] = parentAt(base, parts, true);
  parent[key] = value;
  return base;
}

function applyOperation(root, operation) {
  const op = operation.op;
  const parts = pathParts(operation.path);
  if (op === "patch") {
    let target = parts.length ? clone(targetAt(root, parts)) : clone(root);
    const patches = Array.isArray(operation.value) ? operation.value : [operation.value];
    for (const patch of patches) target = applyOperation(target, expandOperation(patch));
    return setAt(root, parts, target);
  }
  if (!parts.length) {
    if (op === "remove") return undefined;
    if (op === "append") return appendValue(clone(root), operation.value);
    if (op === "truncate") {
      if (typeof root === "string") return root.slice(0, Number(operation.value));
      if (Array.isArray(root)) return root.slice(0, Number(operation.value));
      throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Delta truncate target is not text or an array");
    }
    if (["add", "replace"].includes(op)) return clone(operation.value);
  }
  const base = root == null ? containerFor(parts[0]) : clone(root);
  const [parent, key] = parentAt(base, parts, op === "add");
  if (op === "remove") {
    if (Array.isArray(parent)) parent.splice(Number(key), 1);
    else delete parent[key];
  } else if (op === "append") {
    parent[key] = appendValue(parent[key], operation.value);
  } else if (op === "truncate") {
    if (typeof parent[key] === "string") parent[key] = parent[key].slice(0, Number(operation.value));
    else if (Array.isArray(parent[key])) parent[key] = parent[key].slice(0, Number(operation.value));
    else throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Delta truncate target is not text or an array");
  } else if (op === "add") {
    if (Array.isArray(parent) && key !== "-") parent.splice(Number(key), 0, clone(operation.value));
    else if (Array.isArray(parent)) parent.push(clone(operation.value));
    else parent[key] = clone(operation.value);
  } else if (op === "replace") {
    parent[key] = clone(operation.value);
  } else {
    throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", `Unsupported delta operation: ${String(op)}`);
  }
  return base;
}

function expandOperation(raw, previous = { channel: 0, path: "", op: "add" }) {
  if (!raw || typeof raw !== "object") throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Delta operation is not an object");
  return {
    channel: raw.channel ?? raw.c ?? previous.channel ?? 0,
    path: raw.path ?? raw.p ?? previous.path ?? "",
    op: raw.op ?? raw.o ?? previous.op ?? "add",
    value: Object.hasOwn(raw, "value") ? raw.value : (Object.hasOwn(raw, "v") ? raw.v : undefined),
  };
}

function textualParts(value, output = []) {
  if (typeof value === "string") output.push(value);
  else if (Array.isArray(value)) for (const item of value) textualParts(item, output);
  else if (value && typeof value === "object") {
    if (typeof value.text === "string") output.push(value.text);
    else if (Array.isArray(value.parts)) textualParts(value.parts, output);
    else if (value.content) textualParts(value.content, output);
  }
  return output;
}

function messageText(message) {
  if (!message || message.author?.role !== "assistant") return "";
  const content = message.content;
  if (!content) return "";
  return textualParts(content).join("");
}

class DeltaDecoder {
  constructor() {
    this.encoding = null;
    this.previous = { channel: 0, path: "", op: "add" };
    this.channels = new Map();
    this.visibleText = "";
    this.conversationId = null;
    this.messageId = null;
    this.parentMessageId = null;
    this.sources = [];
    this.toolEvents = [];
    this.complete = false;
  }

  consume({ event, data }) {
    if (data === "[DONE]") return;
    if (event === "delta_encoding") {
      if (data !== "v1") throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", `Unsupported Desktop delta encoding: ${String(data)}`);
      this.encoding = "v1";
      return;
    }
    let decoded = data;
    if (typeof data === "string") {
      try { decoded = JSON.parse(data); }
      catch {
        if (event === "delta") throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Desktop delta is not valid JSON");
      }
    }
    if (event === "delta") {
      if (this.encoding !== "v1") throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Desktop delta arrived before delta_encoding v1");
      const operations = Array.isArray(decoded) ? decoded : [decoded];
      for (const raw of operations) {
        const operation = expandOperation(raw, this.previous);
        if (/tool|function/i.test(String(operation.channel))) {
          this.toolEvents.push({ kind: "server-channel", channel: operation.channel });
        }
        this.previous = operation;
        const current = this.channels.get(operation.channel);
        const next = applyOperation(current, operation);
        this.channels.set(operation.channel, next);
        this._processDecoded(next, null);
      }
      this._refreshVisibleText();
      return;
    }
    this._processDecoded(decoded, event);
  }

  _processDecoded(decoded, event) {
    if (!decoded || typeof decoded !== "object") return;
    if (decoded.error) throw new DesktopRuntimeError("CONVERSATION_REJECTED", "ChatGPT Desktop conversation returned an error");
    this.conversationId = decoded.conversation_id || this.conversationId;
    if (decoded.message) {
      const contentType = decoded.message.content?.content_type;
      const recipient = decoded.message.recipient;
      if ((recipient != null && recipient !== "all") || decoded.message.author?.role === "tool" || /tool|function/i.test(String(contentType || ""))) {
        this.toolEvents.push({
          kind: "server-message",
          recipient: typeof decoded.message.recipient === "string" ? decoded.message.recipient : null,
          content_type: typeof contentType === "string" ? contentType : null,
        });
      } else {
        this.messageId = decoded.message.id || this.messageId;
        this.parentMessageId = decoded.message.id || this.parentMessageId;
        const text = messageText(decoded.message);
        if (text) this.visibleText = text;
      }
      this._collectSources(decoded.message);
    }
    if (event === "message_stream_complete" || decoded.type === "message_stream_complete") this.complete = true;
    this._collectSources(decoded);
  }

  _refreshVisibleText() {
    const preferred = ["final", "analysis", "commentary"];
    for (const name of preferred) {
      if (!this.channels.has(name)) continue;
      const text = textualParts(this.channels.get(name)).join("");
      if (text) { this.visibleText = text; return; }
    }
    for (const value of this.channels.values()) {
      const text = textualParts(value).join("");
      if (text) { this.visibleText = text; return; }
    }
  }

  _collectSources(value) {
    const candidates = value?.metadata?.citations || value?.citations || value?.sources || [];
    if (!Array.isArray(candidates)) return;
    for (const source of candidates) {
      const url = source?.url || source?.metadata?.url;
      const title = source?.title || source?.metadata?.title || url;
      if (typeof url === "string" && !this.sources.some((item) => item.url === url)) this.sources.push({ title: String(title), url });
    }
  }

  result() {
    if (!this.complete) throw new DesktopRuntimeError("STREAM_INTERRUPTED", "Desktop conversation ended without a message completion event");
    if (!this.visibleText.trim()) throw new DesktopRuntimeError("STREAM_INTERRUPTED", "Desktop conversation completed without visible assistant output");
    return {
      text: this.visibleText,
      conversation_id: this.conversationId,
      message_id: this.messageId,
      parent_message_id: this.parentMessageId,
      complete: this.complete,
      sources: this.sources,
      server_tool_events: this.toolEvents,
    };
  }
}

module.exports = { DeltaDecoder, applyOperation, expandOperation, messageText };
