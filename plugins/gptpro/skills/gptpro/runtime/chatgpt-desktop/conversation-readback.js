"use strict";

const { runtimeError } = require("./errors.js");

const LIST_LIMIT = 20;
const DEFAULT_POLL_INTERVAL_MS = 1_000;
const DEFAULT_LOOKBACK_MS = 120_000;

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function abortReason(signal) {
  const reason = signal?.reason;
  return reason && typeof reason === "object" && typeof reason.code === "string"
    ? reason
    : runtimeError("CANCELLED", "Desktop response collection was cancelled.", { submissionState: "ambiguous" });
}

function sleep(ms, signal) {
  if (signal?.aborted) return Promise.reject(abortReason(signal));
  return new Promise((resolve, reject) => {
    const finish = (callback, value) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      callback(value);
    };
    const abort = () => finish(reject, abortReason(signal));
    const timer = setTimeout(() => finish(resolve), ms);
    signal?.addEventListener("abort", abort, { once: true });
  });
}

function timestampMs(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value > 10_000_000_000 ? value : value * 1_000;
  if (typeof value !== "string") return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function currentBranch(conversation) {
  const mapping = conversation?.mapping;
  if (!object(mapping) || typeof conversation?.current_node !== "string") {
    throw runtimeError("RESPONSE_READBACK_CONTRACT_CHANGED", "The Desktop conversation detail contract is unavailable.", { submissionState: "ambiguous" });
  }
  const reversed = [];
  const seen = new Set();
  let cursor = conversation.current_node;
  while (typeof cursor === "string" && cursor && !seen.has(cursor)) {
    seen.add(cursor);
    const node = mapping[cursor];
    if (!object(node)) {
      throw runtimeError("RESPONSE_READBACK_CONTRACT_CHANGED", "The Desktop conversation branch is incomplete.", { submissionState: "ambiguous" });
    }
    reversed.push(node);
    cursor = typeof node.parent === "string" ? node.parent : null;
  }
  return reversed.reverse();
}

function responseFromConversation(conversation, { messageId, prompt }) {
  const branch = currentBranch(conversation);
  const index = branch.findIndex((node) => node?.message?.id === messageId);
  if (index < 0) return null;
  const user = branch[index]?.message;
  if (
    user?.author?.role !== "user"
    || user?.content?.content_type !== "text"
    || user.content.parts?.[0] !== prompt
  ) {
    throw runtimeError("RESPONSE_CORRELATION_MISMATCH", "The Desktop conversation message ID did not match the approved outbound bytes.", { submissionState: "ambiguous" });
  }

  let final = null;
  for (const node of branch.slice(index + 1)) {
    const message = node?.message;
    if (!object(message)) continue;
    if (
      message.author?.role === "tool"
      || (message.author?.role === "assistant" && typeof message.recipient === "string" && message.recipient !== "all")
    ) {
      throw runtimeError("UNEXPECTED_TOOL_ROUTE", "The matched Desktop conversation used a prohibited tool route.", { submissionState: "ambiguous" });
    }
    if (
      message.author?.role === "assistant"
      && message.channel === "final"
      && message.content?.content_type === "text"
      && typeof message.content.parts?.[0] === "string"
    ) {
      final = message;
    }
  }
  if (!final || final.status !== "finished_successfully" || final.end_turn !== true) {
    return { pending: true };
  }
  const text = final.content.parts[0];
  return {
    pending: false,
    text,
    conversation_id: typeof conversation.id === "string" ? conversation.id : null,
    parent_message_id: typeof final.id === "string" ? final.id : null,
    assistant_message_id: typeof final.id === "string" ? final.id : null,
    tool_routes: 0,
    completion_source: "conversation-readback-v1",
  };
}

async function requestJson(bridge, method, url, { headers, signal, timeoutMs }) {
  const response = await bridge.request(method, url, { headers, signal, timeoutMs });
  if (response.status < 200 || response.status >= 300) {
    throw runtimeError("RESPONSE_READBACK_UNAVAILABLE", `Desktop response readback returned HTTP ${response.status}.`, { submissionState: "ambiguous" });
  }
  if (!object(response.body)) {
    throw runtimeError("RESPONSE_READBACK_CONTRACT_CHANGED", "Desktop response readback returned an invalid body.", { submissionState: "ambiguous" });
  }
  return response.body;
}

async function waitForConversationResponse(bridge, options) {
  const signal = options.signal;
  const headers = options.headers;
  const messageId = options.messageId;
  const prompt = options.prompt;
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const requestTimeoutMs = options.requestTimeoutMs ?? 30_000;
  const notBeforeMs = (options.notBeforeMs ?? Date.now()) - (options.lookbackMs ?? DEFAULT_LOOKBACK_MS);
  const seenUpdates = new Map();
  let matchedConversationId = null;

  while (true) {
    if (signal?.aborted) throw abortReason(signal);
    const candidates = [];
    if (matchedConversationId) {
      candidates.push({ id: matchedConversationId, update_time: null, matched: true });
    } else {
      const list = await requestJson(
        bridge,
        "GET",
        `/conversations?offset=0&limit=${LIST_LIMIT}&order=updated`,
        { headers, signal, timeoutMs: requestTimeoutMs },
      );
      if (!Array.isArray(list.items)) {
        throw runtimeError("RESPONSE_READBACK_CONTRACT_CHANGED", "The Desktop conversation list contract is unavailable.", { submissionState: "ambiguous" });
      }
      for (const item of list.items.slice(0, LIST_LIMIT)) {
        if (!object(item) || typeof item.id !== "string" || !item.id) continue;
        const updated = timestampMs(item.update_time ?? item.create_time);
        if (updated !== null && updated < notBeforeMs) continue;
        const updateKey = String(item.update_time ?? item.create_time ?? "");
        if (seenUpdates.get(item.id) === updateKey) continue;
        seenUpdates.set(item.id, updateKey);
        candidates.push(item);
      }
    }

    const matches = [];
    for (const candidate of candidates) {
      const detail = await requestJson(
        bridge,
        "GET",
        `/conversation/${encodeURIComponent(candidate.id)}`,
        { headers, signal, timeoutMs: requestTimeoutMs },
      );
      const correlated = responseFromConversation(detail, { messageId, prompt });
      if (correlated) matches.push({ id: candidate.id, result: correlated });
    }
    if (matches.length > 1) {
      throw runtimeError("RESPONSE_CORRELATION_AMBIGUOUS", "More than one Desktop conversation matched the deterministic message ID.", { submissionState: "ambiguous" });
    }
    if (matches.length === 1) {
      matchedConversationId = matches[0].id;
      if (!matches[0].result.pending) {
        return {
          ...matches[0].result,
          conversation_id: matches[0].result.conversation_id ?? matches[0].id,
        };
      }
    }
    await sleep(pollIntervalMs, signal);
  }
}

module.exports = {
  DEFAULT_LOOKBACK_MS,
  DEFAULT_POLL_INTERVAL_MS,
  LIST_LIMIT,
  currentBranch,
  responseFromConversation,
  timestampMs,
  waitForConversationResponse,
};
