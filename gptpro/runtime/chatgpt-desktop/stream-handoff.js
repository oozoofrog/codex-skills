"use strict";

const crypto = require("node:crypto");
const { AsyncQueue } = require("./async-queue.js");
const { parseSse } = require("./delta-decoder.js");
const { runtimeError } = require("./errors.js");

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function handoffTopic(value) {
  if (!object(value) || value.type !== "stream_handoff" || !Array.isArray(value.options)) return null;
  const topics = value.options
    .filter((item) => item?.type === "subscribe_ws_topic" && typeof item.topic_id === "string" && item.topic_id)
    .map((item) => item.topic_id);
  if (topics.length !== 1 || topics[0].length > 4096) {
    throw runtimeError("STREAM_HANDOFF_INVALID", "The Desktop stream handoff did not contain exactly one valid topic.", { submissionState: "ambiguous" });
  }
  return topics[0];
}

function topicHash(topicId) {
  return crypto.createHash("sha256").update(`gptpro-stream-topic-v1\0${topicId}`, "utf8").digest("hex");
}

class StreamHandoff {
  constructor(socket, topicId) {
    this.socket = socket;
    this.topicId = topicId;
    this.topicSha256 = topicHash(topicId);
    this.events = new AsyncQueue();
    this.seenItems = new Set();
    this.subscribed = false;
    this.terminal = false;
    void this.#pump();
  }

  static async connect(bridge, signedUrl, topicId, options = {}) {
    const socket = await bridge.openWebSocket(signedUrl, {
      signal: options.signal,
      connectTimeoutMs: options.connectTimeoutMs ?? 5_000,
    });
    const handoff = new StreamHandoff(socket, topicId);
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
    this.events.end();
    await this.socket.close();
  }

  async fail(cause) {
    if (this.terminal) return;
    this.terminal = true;
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
        ) {
          throw runtimeError("STREAM_HANDOFF_RECOVERY_FAILED", "The Desktop handoff could not recover the requested stream topic.", { submissionState: "ambiguous" });
        }
        if (this.subscribed) {
          throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff acknowledged its subscription more than once.", { submissionState: "ambiguous" });
        }
        this.subscribed = true;
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
    const envelope = entry?.payload;
    if (!object(envelope) || envelope.type !== "conversation-turn-stream") return;
    const payload = envelope.payload;
    if (!object(payload)) return;
    if (payload.type === "heartbeat") return;
    if (payload.type === "done") {
      this.terminal = true;
      this.events.end();
      void this.socket.close();
      return;
    }
    if (payload.type !== "stream-item" || typeof payload.encoded_item !== "string") return;

    if (payload.parent_stream_item_id != null && !this.seenItems.has(payload.parent_stream_item_id)) {
      throw runtimeError("STREAM_PROTOCOL_ERROR", "The Desktop handoff stream-item parent chain is incomplete.", { submissionState: "ambiguous" });
    }
    if (payload.stream_item_id != null) {
      if (this.seenItems.has(payload.stream_item_id)) return;
      this.seenItems.add(payload.stream_item_id);
    }
    for (const event of parseSse(payload.encoded_item)) this.events.push(event);
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
