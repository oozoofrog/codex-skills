"use strict";

const { runtimeError } = require("./errors.js");

const OPEN = "\uE200";
const SEPARATOR = "\uE202";
const CLOSE = "\uE201";

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  return value === undefined ? undefined : structuredClone(value);
}

function pointer(path) {
  if (!path) return [];
  const raw = String(path);
  if (raw.length > 16 * 1024) throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta path is too large.", { submissionState: "ambiguous" });
  const segments = raw.replace(/^\//, "").split("/").map((part) => {
    const decoded = part.replaceAll("~1", "/").replaceAll("~0", "~");
    if (["__proto__", "prototype", "constructor"].includes(decoded)) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta path is unsafe.", { submissionState: "ambiguous" });
    }
    if (/^(0|[1-9]\d*)$/.test(decoded)) {
      const index = Number(decoded);
      if (!Number.isSafeInteger(index) || index > 1_000_000) throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta index is unsafe.", { submissionState: "ambiguous" });
      return index;
    }
    return decoded;
  });
  if (segments.length > 128) throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta path is too deep.", { submissionState: "ambiguous" });
  return segments;
}

function expand(delta, previous) {
  const mapping = { c: "channel", p: "path", o: "op", v: "value" };
  const result = {};
  for (const [key, value] of Object.entries(delta)) result[mapping[key] ?? key] = value;
  for (const key of ["channel", "path", "op"]) if (!(key in result)) result[key] = previous[key];
  if (result.op === "patch" && Array.isArray(result.value)) result.value = result.value.map((item) => expand(item, {}));
  return result;
}

function applyAt(root, delta) {
  if (!["add", "replace", "append", "patch", "remove", "truncate"].includes(delta.op)) {
    throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta stream used an unknown operation.", { submissionState: "ambiguous" });
  }
  const segments = pointer(delta.path);
  if (!segments.length) {
    if (delta.op === "add" || delta.op === "replace" || delta.op === "append") {
      if (delta.op === "append" && typeof root === "string") return root + delta.value;
      return clone(delta.value);
    }
    if (delta.op === "patch") {
      let next = clone(root);
      for (const child of delta.value) next = applyAt(next, child);
      return next;
    }
    if (delta.op === "remove") return undefined;
    if (delta.op === "truncate") return typeof root === "string" ? root.slice(0, delta.value) : Array.isArray(root) ? root.slice(0, delta.value) : root;
  }
  let next = clone(root);
  if (next === undefined || next === null || typeof next !== "object") next = typeof segments[0] === "number" ? [] : {};
  let target = next;
  for (let index = 0; index < segments.length - 1; index += 1) {
    const segment = segments[index];
    if (target[segment] === undefined) target[segment] = typeof segments[index + 1] === "number" ? [] : {};
    target = target[segment];
  }
  const leaf = segments.at(-1);
  if (delta.op === "patch") {
    let value = target[leaf];
    for (const child of delta.value) value = applyAt(value, child);
    target[leaf] = value;
  } else if (delta.op === "add") {
    if (Array.isArray(target)) target.splice(leaf, 0, clone(delta.value));
    else target[leaf] = clone(delta.value);
  } else if (delta.op === "replace") target[leaf] = clone(delta.value);
  else if (delta.op === "remove") Array.isArray(target) ? target.splice(leaf, 1) : delete target[leaf];
  else if (delta.op === "append") {
    const current = target[leaf];
    if (typeof current === "string") target[leaf] = current + delta.value;
    else if (Array.isArray(current)) current.push(...(Array.isArray(delta.value) ? delta.value : [delta.value]));
    else if (object(current) && object(delta.value)) Object.assign(current, delta.value);
    else target[leaf] = clone(delta.value);
  } else if (delta.op === "truncate") {
    if (typeof target[leaf] === "string") target[leaf] = target[leaf].slice(0, delta.value);
    else if (Array.isArray(target[leaf])) target[leaf].length = delta.value;
  } else throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta stream used an unknown operation.", { submissionState: "ambiguous" });
  return next;
}

class DeltaState {
  constructor() {
    this.channels = [];
    this.previous = { channel: 0, path: "", op: "add" };
  }

  apply(value) {
    if (!object(value)) throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta is not an object.", { submissionState: "ambiguous" });
    const delta = expand(value, this.previous);
    if (!Number.isSafeInteger(delta.channel) || delta.channel < 0 || delta.channel > 64) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta channel is invalid.", { submissionState: "ambiguous" });
    }
    this.previous = delta;
    this.channels[delta.channel] = applyAt(this.channels[delta.channel], delta);
    return this.channels[delta.channel];
  }
}

function visibleText(raw) {
  let result = "";
  let hidden = false;
  for (const character of String(raw ?? "")) {
    if (character === OPEN || character === SEPARATOR) hidden = true;
    else if (character === CLOSE) hidden = false;
    else if (!hidden) result += character;
  }
  return result;
}

function assertNoToolRoute(message, requireRecipient = false) {
  if (
    message?.author?.role === "tool"
    || (message?.author?.role === "assistant" && message.recipient != null && message.recipient !== "all")
    || (requireRecipient && message?.author?.role === "assistant" && message.recipient !== "all")
  ) {
    throw runtimeError(
      "UNEXPECTED_TOOL_ROUTE",
      "ChatGPT selected a local, server, app, search, connector, or other tool route during an inline-only consultation.",
      { submissionState: "ambiguous" },
    );
  }
}

class ConversationDecoder {
  constructor() {
    this.delta = null;
    this.reset();
  }

  reset() {
    this.conversationId = null;
    this.parentMessageId = null;
    this.assistantMessageId = null;
    this.finalText = "";
    this.finalRecipientAll = false;
    this.toolRouteCandidate = false;
    this.preHandoffAssistantEvidence = false;
    this.preHandoffDeltaSeen = false;
    this.signedDeltaEncodingSeen = false;
    this.signedDeltaContinuationObserved = false;
    this.signedAssistantEvidence = false;
    this.done = false;
  }

  consume(event, data, options = {}) {
    const signed = options.signed === true;
    if (event === "delta_encoding") {
      if (String(data) !== "v1") throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop delta encoding is unsupported.", { submissionState: "ambiguous" });
      this.delta = new DeltaState();
      if (signed) this.signedDeltaEncodingSeen = true;
      return null;
    }
    let value = data;
    if (event === "delta") {
      if (!this.delta) throw runtimeError("STREAM_PROTOCOL_ERROR", "A Desktop delta arrived before its encoding.", { submissionState: "ambiguous" });
      if (signed && this.preHandoffDeltaSeen && !this.signedDeltaEncodingSeen) {
        this.signedDeltaContinuationObserved = true;
      } else if (!signed) {
        this.preHandoffDeltaSeen = true;
      }
      value = this.delta.apply(data);
    }
    if (data === "[DONE]") { this.done = true; return data; }
    this.#observe(value, signed);
    return value;
  }

  #observe(value, signed) {
    if (!object(value)) return;
    if (typeof value.conversation_id === "string") this.conversationId = value.conversation_id;
    if (value.type === "message_stream_complete") this.done = true;
    const message = value.message;
    if (!object(message)) return;
    if (!signed && message.author?.role === "assistant") this.preHandoffAssistantEvidence = true;
    if (message.author?.role === "tool") {
      this.toolRouteCandidate = true;
      return;
    }
    assertNoToolRoute(message);
    if (message.author?.role === "assistant" && message.channel === "final" && message.content?.content_type === "text") {
      if (
        message.content.parts !== undefined
        && (
          !Array.isArray(message.content.parts)
          || message.content.parts.length > 1
          || (message.content.parts.length === 1 && typeof message.content.parts[0] !== "string")
        )
      ) {
        throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop final assistant content shape is unsupported.", { submissionState: "ambiguous" });
      }
      this.finalText = visibleText(message.content.parts?.[0] ?? "");
      this.finalRecipientAll = message.recipient === "all";
      this.assistantMessageId = typeof message.id === "string" ? message.id : null;
      this.parentMessageId = this.assistantMessageId;
      if (signed && this.finalText.trim().length > 0 && this.finalRecipientAll && this.assistantMessageId) {
        this.signedAssistantEvidence = true;
      }
      if (message.status === "finished_successfully" && message.end_turn === true) {
        assertNoToolRoute(message, true);
        this.done = true;
      }
    }
  }

  finish(options = {}) {
    return {
      text: this.finalText,
      conversation_id: this.conversationId,
      parent_message_id: this.parentMessageId,
      assistant_message_id: this.assistantMessageId,
      tool_routes: 0,
      done: (this.done || options.transportDone === true)
        && this.finalText.trim().length > 0
        && this.finalRecipientAll
        && typeof this.assistantMessageId === "string",
    };
  }
}

function parseSse(value) {
  const events = [];
  for (const block of String(value).replaceAll("\r\n", "\n").split("\n\n")) {
    let event;
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) continue;
    const raw = data.join("\n").trim();
    if (raw === "[DONE]") events.push({ event, data: raw });
    else {
      try { events.push({ event, data: JSON.parse(raw) }); } catch {
        throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop SSE stream contained invalid JSON.", { submissionState: "ambiguous" });
      }
    }
  }
  return events;
}

module.exports = { ConversationDecoder, DeltaState, applyAt, assertNoToolRoute, expand, parseSse, visibleText };
