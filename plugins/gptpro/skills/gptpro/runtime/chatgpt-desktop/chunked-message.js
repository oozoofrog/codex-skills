"use strict";

const { DesktopRuntimeError } = require("./errors");

const MARKER = "codex-host-chunked-message-v1";
const UNSET = Symbol("unset");

function isChunkFrame(value) {
  return Boolean(value && typeof value === "object" && value.marker === MARKER);
}

class TokenBuilder {
  constructor() {
    this.stack = [];
    this.root = UNSET;
    this.string = null;
  }

  saveValue(value) {
    if (!this.stack.length) {
      if (this.root !== UNSET) throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Chunked message has multiple root values");
      this.root = value;
      return;
    }
    const frame = this.stack[this.stack.length - 1];
    if (Array.isArray(frame.value)) {
      frame.value.push(value);
      return;
    }
    if (frame.pendingKey === UNSET) throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Chunked object value has no key");
    Object.defineProperty(frame.value, frame.pendingKey, { value, enumerable: true, configurable: true, writable: true });
    frame.pendingKey = UNSET;
  }

  feed(token) {
    if (!token || typeof token !== "object") throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Invalid chunk token");
    switch (token.type) {
      case "array-start": {
        const value = [];
        this.saveValue(value);
        this.stack.push({ value, pendingKey: UNSET });
        break;
      }
      case "object-start": {
        const value = {};
        this.saveValue(value);
        this.stack.push({ value, pendingKey: UNSET });
        break;
      }
      case "container-end":
        if (!this.stack.length || this.string || this.stack[this.stack.length - 1].pendingKey !== UNSET) {
          throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Unexpected chunk container end");
        }
        this.stack.pop();
        break;
      case "key": {
        const frame = this.stack[this.stack.length - 1];
        if (!frame || Array.isArray(frame.value) || frame.pendingKey !== UNSET || typeof token.value !== "string") {
          throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Invalid chunk object key");
        }
        frame.pendingKey = token.value;
        break;
      }
      case "value":
        this.saveValue(Object.hasOwn(token, "value") ? token.value : undefined);
        break;
      case "string-start":
        if (this.string || !new Set(["key", "value"]).has(token.target)) {
          throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Invalid chunk string start");
        }
        this.string = { target: token.target, value: "" };
        break;
      case "string-chunk":
        if (!this.string || typeof token.value !== "string") throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Invalid chunk string data");
        this.string.value += token.value;
        break;
      case "string-end": {
        if (!this.string) throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Chunk string end without start");
        const completed = this.string;
        this.string = null;
        if (completed.target === "key") this.feed({ type: "key", value: completed.value });
        else this.saveValue(completed.value);
        break;
      }
      default:
        throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", `Unsupported chunk token: ${String(token.type)}`);
    }
  }

  finish() {
    if (this.root === UNSET || this.stack.length || this.string ||
        this.stack.some((frame) => frame.pendingKey !== UNSET)) {
      throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Incomplete chunked message");
    }
    return this.root;
  }
}

class ChunkedMessageAssembler {
  constructor({ acknowledge = async () => {} } = {}) {
    this.acknowledge = acknowledge;
    this.transfers = new Map();
  }

  async accept(message) {
    if (!isChunkFrame(message)) return { complete: true, value: message };
    const { transferId, sequence, kind } = message;
    if (typeof transferId !== "string" || !Number.isSafeInteger(sequence) ||
        !new Set(["start", "chunk", "end"]).has(kind)) {
      throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Invalid chunk frame identity");
    }
    if (kind === "start") {
      this.transfers.clear();
      this.transfers.set(transferId, { next: sequence + 1, builder: new TokenBuilder() });
      await this.acknowledge(transferId, sequence);
      return { complete: false };
    }
    const transfer = this.transfers.get(transferId);
    if (!transfer || sequence !== transfer.next) {
      this.transfers.delete(transferId);
      throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Chunk frame sequence gap");
    }
    if (kind === "chunk") {
      if (!Array.isArray(message.tokens)) throw new DesktopRuntimeError("STREAM_PROTOCOL_ERROR", "Chunk frame tokens are invalid");
      for (const token of message.tokens) transfer.builder.feed(token);
      transfer.next += 1;
      await this.acknowledge(transferId, sequence);
      return { complete: false };
    }
    this.transfers.delete(transferId);
    const value = transfer.builder.finish();
    await this.acknowledge(transferId, sequence);
    return { complete: true, value };
  }
}

function rendererRelaySource(bindingName, responseTypes) {
  return `(${function installRelay(binding, marker, allowedTypes) {
    if (window.__gptproDesktopListenerInstalled) return true;
    const UNSET_VALUE = Symbol("unset");
    class Builder {
      constructor() { this.stack = []; this.root = UNSET_VALUE; this.string = null; }
      save(value) {
        if (!this.stack.length) { if (this.root !== UNSET_VALUE) throw new Error("multiple roots"); this.root = value; return; }
        const frame = this.stack[this.stack.length - 1];
        if (Array.isArray(frame.value)) { frame.value.push(value); return; }
        if (frame.key === UNSET_VALUE) throw new Error("missing key");
        Object.defineProperty(frame.value, frame.key, { value, enumerable: true, configurable: true, writable: true });
        frame.key = UNSET_VALUE;
      }
      feed(token) {
        if (!token || typeof token !== "object") throw new Error("invalid token");
        if (token.type === "array-start" || token.type === "object-start") {
          const value = token.type === "array-start" ? [] : {}; this.save(value); this.stack.push({ value, key: UNSET_VALUE }); return;
        }
        if (token.type === "container-end") {
          if (!this.stack.length || this.string || this.stack[this.stack.length - 1].key !== UNSET_VALUE) throw new Error("invalid end");
          this.stack.pop(); return;
        }
        if (token.type === "key") {
          const frame = this.stack[this.stack.length - 1];
          if (!frame || Array.isArray(frame.value) || frame.key !== UNSET_VALUE || typeof token.value !== "string") throw new Error("invalid key");
          frame.key = token.value; return;
        }
        if (token.type === "value") { this.save(Object.prototype.hasOwnProperty.call(token, "value") ? token.value : undefined); return; }
        if (token.type === "string-start") {
          if (this.string || (token.target !== "key" && token.target !== "value")) throw new Error("invalid string");
          this.string = { target: token.target, value: "" }; return;
        }
        if (token.type === "string-chunk") { if (!this.string || typeof token.value !== "string") throw new Error("invalid string chunk"); this.string.value += token.value; return; }
        if (token.type === "string-end") {
          if (!this.string) throw new Error("invalid string end"); const complete = this.string; this.string = null;
          if (complete.target === "key") this.feed({ type: "key", value: complete.value }); else this.save(complete.value); return;
        }
        throw new Error("unknown token");
      }
      finish() { if (this.root === UNSET_VALUE || this.stack.length || this.string) throw new Error("incomplete"); return this.root; }
    }
    let transfer = null;
    const forward = (data) => {
      if (data && allowedTypes.includes(data.type) && typeof data.requestId === "string" && window.__gptproDesktopRequestIds.has(data.requestId)) {
        window[binding](JSON.stringify(data));
      }
    };
    Object.defineProperty(window, "__gptproDesktopListenerInstalled", { value: true, configurable: false });
    Object.defineProperty(window, "__gptproDesktopRequestIds", { value: new Set(), configurable: false });
    window.addEventListener("message", (event) => {
      const data = event.data;
      if (!data || data.marker !== marker) { forward(data); return; }
      try {
        if (typeof data.transferId !== "string" || !Number.isSafeInteger(data.sequence) || !["start", "chunk", "end"].includes(data.kind)) return;
        if (data.kind === "start") { transfer = { id: data.transferId, next: data.sequence + 1, builder: new Builder() }; return; }
        if (!transfer || transfer.id !== data.transferId || transfer.next !== data.sequence) { transfer = null; return; }
        if (data.kind === "chunk") {
          if (!Array.isArray(data.tokens)) { transfer = null; return; }
          for (const token of data.tokens) transfer.builder.feed(token);
          transfer.next += 1; return;
        }
        const completed = transfer.builder.finish(); transfer = null; forward(completed);
      } catch (_) { transfer = null; }
    });
    return true;
  }.toString()})(${JSON.stringify(bindingName)}, ${JSON.stringify(MARKER)}, ${JSON.stringify(responseTypes)})`;
}

module.exports = { MARKER, TokenBuilder, ChunkedMessageAssembler, isChunkFrame, rendererRelaySource };
