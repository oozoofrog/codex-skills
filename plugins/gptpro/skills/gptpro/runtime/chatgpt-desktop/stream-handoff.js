"use strict";

const crypto = require("node:crypto");
const { AsyncQueue } = require("./async-queue.js");
const { parseSse } = require("./delta-decoder.js");
const { runtimeError } = require("./errors.js");

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function identifier(value) {
  return typeof value === "string" && value.length > 0;
}

function handoffTopic(value) {
  if (!object(value) || value.type !== "stream_handoff" || !Array.isArray(value.options)) return null;
  if (!identifier(value.turn_exchange_id)) {
    throw runtimeError("STREAM_HANDOFF_INVALID", "The Desktop stream handoff did not contain a valid turn exchange.", { submissionState: "ambiguous" });
  }
  const topics = value.options
    .filter((item) => item?.type === "subscribe_ws_topic" && typeof item.topic_id === "string" && item.topic_id)
    .map((item) => item.topic_id);
  if (topics.length !== 1 || !/^conversation-.+/.test(topics[0]) || topics[0].length > 4096) {
    throw runtimeError("STREAM_HANDOFF_INVALID", "The Desktop stream handoff did not contain exactly one valid topic.", { submissionState: "ambiguous" });
  }
  return topics[0];
}

function topicHash(topicId) {
  return crypto.createHash("sha256").update(`gptpro-stream-topic-v1\0${topicId}`, "utf8").digest("hex");
}

class StreamHandoff {
  constructor(socket, topicId, options = {}) {
    this.socket = socket;
    this.topicId = topicId;
    this.topicSha256 = topicHash(topicId);
    this.initialTimeoutMs = options.initialTimeoutMs ?? 5_000;
    this.idleTimeoutMs = options.idleTimeoutMs ?? 30_000;
    this.events = new AsyncQueue();
    this.seenItems = new Set();
    this.subscribed = false;
    this.conversationId = null;
    this.turnId = null;
    this.completed = false;
    this.terminal = false;
    this.timer = null;
    this.#armTimeout(false);
    void this.#pump();
  }

  static async connect(bridge, signedUrl, topicId, options = {}) {
    const socket = await bridge.openWebSocket(signedUrl, {
      signal: options.signal,
      connectTimeoutMs: options.connectTimeoutMs ?? 5_000,
    });
    const handoff = new StreamHandoff(socket, topicId, options);
    try {
      await socket.send(JSON.stringify([
        { id: 1, command: { type: "connect", presence: { type: "presence", state: "foreground" } } },
        { id: 2, command: { type: "subscribe", topic_id: topicId, offset: "0" } },
      ]));
      return handoff;
    } catch (error) {
      await handoff.fail(error);
      throw error;
    }
  }

  async close() {
    if (this.terminal) return;
    this.terminal = true;
    clearTimeout(this.timer);
    this.events.end();
    await this.socket.close();
  }

  async fail(cause) {
    if (this.terminal) return;
    this.terminal = true;
    clearTimeout(this.timer);
    const error = cause?.code
      ? cause
      : runtimeError("STREAM_INTERRUPTED", "The Desktop handoff ended before a proven completion.", { cause, submissionState: "ambiguous" });
    this.events.fail(error);
    await this.socket.close();
  }

  async #pump() {
    try {
      for await (const raw of this.socket.events) {
        if (this.terminal) return;
        if (object(raw) && raw.type === "close") {
          throw runtimeError("STREAM_INTERRUPTED", "The Desktop handoff WebSocket closed before completion.", { submissionState: "ambiguous" });
        }
        this.#consumeFrame(raw);
      }
      if (!this.terminal) {
        throw runtimeError("STREAM_INTERRUPTED", "The Desktop handoff WebSocket ended before completion.", { submissionState: "ambiguous" });
      }
    } catch (error) {
      await this.fail(error);
    }
  }

  #armTimeout(idle) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.fail(runtimeError(
      idle ? "STREAM_HANDOFF_IDLE_TIMEOUT" : "STREAM_HANDOFF_INITIAL_TIMEOUT",
      idle
        ? "The Desktop handoff WebSocket stopped producing stream data."
        : "The Desktop handoff WebSocket produced no initial stream data.",
      { submissionState: "ambiguous" },
    )), idle ? this.idleTimeoutMs : this.initialTimeoutMs);
  }

  #consumeFrame(raw) {
    let frame;
    try { frame = JSON.parse(String(raw)); } catch (cause) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff WebSocket returned invalid JSON.", { cause, submissionState: "ambiguous" });
    }
    for (const entry of Array.isArray(frame) ? frame : [frame]) {
      if (entry?.id === 2) {
        const reply = entry.reply;
        if (
          !object(reply)
          || reply.type !== "subscribe"
          || reply.topic_id !== this.topicId
          || reply.recovered !== true
          || (reply.catchups !== undefined && !Array.isArray(reply.catchups))
          || (reply.last_offset !== undefined && typeof reply.last_offset !== "string")
        ) {
          throw runtimeError("STREAM_HANDOFF_RECOVERY_FAILED", "The Desktop handoff could not recover the requested stream topic.", { submissionState: "ambiguous" });
        }
        if (this.subscribed) {
          throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff acknowledged its subscription more than once.", { submissionState: "ambiguous" });
        }
        this.subscribed = true;
        this.#armTimeout(false);
        for (const catchup of reply.catchups ?? []) this.#consumeTopicMessage(catchup);
        continue;
      }
      if (entry?.type === "message" && entry.topic_id === this.topicId) {
        if (!this.subscribed) {
          throw runtimeError("STREAM_HANDOFF_RECOVERY_FAILED", "The Desktop handoff emitted data before confirming recovery.", { submissionState: "ambiguous" });
        }
        this.#consumeTopicMessage(entry);
      }
    }
  }

  #consumeTopicMessage(entry) {
    if (entry?.type !== "message" || entry.topic_id !== this.topicId || (entry.offset !== undefined && typeof entry.offset !== "string")) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff returned an invalid topic message.", { submissionState: "ambiguous" });
    }
    const envelope = entry?.payload;
    if (!object(envelope) || envelope.type !== "conversation-turn-stream") {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff returned an invalid conversation stream envelope.", { submissionState: "ambiguous" });
    }
    const payload = envelope.payload;
    if (!object(payload) || !identifier(payload.turn_id)) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff returned an invalid conversation stream payload.", { submissionState: "ambiguous" });
    }
    if (this.turnId === null) this.turnId = payload.turn_id;
    else if (this.turnId !== payload.turn_id) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff mixed multiple turn identities.", { submissionState: "ambiguous" });
    }
    if (payload.conversation_id != null) {
      if (!identifier(payload.conversation_id)) {
        throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff returned an invalid conversation identity.", { submissionState: "ambiguous" });
      }
      if (this.conversationId === null) this.conversationId = payload.conversation_id;
      else if (this.conversationId !== payload.conversation_id) {
        throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff mixed multiple conversation identities.", { submissionState: "ambiguous" });
      }
    }
    this.#armTimeout(true);
    if (payload.type === "heartbeat") return;
    if (payload.type === "done") {
      if (!identifier(payload.conversation_id)) {
        throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff completion omitted its conversation identity.", { submissionState: "ambiguous" });
      }
      this.completed = true;
      this.terminal = true;
      clearTimeout(this.timer);
      this.events.end();
      void this.socket.close();
      return;
    }
    if (
      payload.type !== "stream-item"
      || !identifier(payload.conversation_id)
      || typeof payload.encoded_item !== "string"
      || !("stream_item_id" in payload)
      || !("parent_stream_item_id" in payload)
      || (payload.stream_item_id !== null && !identifier(payload.stream_item_id))
      || (payload.parent_stream_item_id !== null && !identifier(payload.parent_stream_item_id))
    ) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff returned an invalid stream item.", { submissionState: "ambiguous" });
    }

    if (payload.parent_stream_item_id != null && !this.seenItems.has(payload.parent_stream_item_id)) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff stream-item parent chain is incomplete.", { submissionState: "ambiguous" });
    }
    if (payload.stream_item_id != null) {
      if (this.seenItems.has(payload.stream_item_id)) return;
    }
    const events = parseSse(payload.encoded_item);
    if (events.length === 0 && payload.encoded_item.trim() !== "data: [DONE]") {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff stream item did not contain a valid SSE event.", { submissionState: "ambiguous" });
    }
    if (events.some((event) => object(event.data) && typeof event.data.error === "string" && event.data.error.length > 0)) {
      throw runtimeError("STREAM_INTERRUPTED", "The Desktop handoff reported a response error.", { submissionState: "ambiguous" });
    }
    if (payload.stream_item_id != null) this.seenItems.add(payload.stream_item_id);
    for (const event of events) this.events.push(event);
  }
}

async function openStreamHandoff(bridge, topicId, options = {}) {
  const response = await bridge.request("GET", "/celsius/ws/user", {
    headers: options.headers,
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? 30_000,
  });
  if (response.status < 200 || response.status >= 300) {
    throw runtimeError("STREAM_HANDOFF_URL_UNAVAILABLE", `The Desktop handoff URL request returned HTTP ${response.status}.`, { submissionState: "ambiguous" });
  }
  const signedUrl = response.body?.websocket_url;
  if (typeof signedUrl !== "string" || !signedUrl) {
    throw runtimeError("STREAM_HANDOFF_URL_UNAVAILABLE", "The Desktop handoff URL response was unavailable.", { submissionState: "ambiguous" });
  }
  return StreamHandoff.connect(bridge, signedUrl, topicId, options);
}

module.exports = { StreamHandoff, handoffTopic, openStreamHandoff, topicHash };
