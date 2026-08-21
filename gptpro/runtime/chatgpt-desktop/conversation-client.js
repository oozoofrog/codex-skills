"use strict";

const crypto = require("node:crypto");
const { DesktopRuntimeError } = require("./errors");
const { DEVICE_CHECK_HEADERS } = require("./desktop-bridge");
const { DeltaDecoder } = require("./delta-decoder");
const { normalizeDesktopCatalog, resolveDesktopModel, resolveThinkingEffort } = require("./model-catalog");

class ChatGptDesktopConversationClient {
  constructor(bridge) { this.bridge = bridge; }

  async prepareIntegrity({ signal } = {}) {
    const response = await this.bridge.request({
      method: "GET",
      url: "/ios/attestation_challenge",
      headers: DEVICE_CHECK_HEADERS,
      signal,
      errorCode: "DEVICE_CHECK_UNAVAILABLE",
    });
    if (!Number.isInteger(response.status) || response.status < 200 || response.status >= 300 ||
        !response.body || typeof response.body.attestation_challenge !== "string" ||
        !response.body.attestation_challenge.trim()) {
      throw new DesktopRuntimeError("DEVICE_CHECK_UNAVAILABLE", "Desktop integrity challenge is unavailable");
    }
    return response.body.attestation_challenge;
  }

  async getAvailableModels({ signal } = {}) {
    const response = await this.bridge.request({
      method: "GET",
      url: "/models?iim=false&include_icons=false",
      signal,
      errorCode: "MODEL_CATALOG_FAILED",
    });
    if (!Number.isInteger(response.status) || response.status < 200 || response.status >= 300) {
      throw new DesktopRuntimeError("MODEL_CATALOG_FAILED", `Desktop model catalog failed with HTTP ${response.status}`);
    }
    return normalizeDesktopCatalog(response.body);
  }

  async startChat({ prompt, model: requestedModel, thinkingEffort = null, signal, continuation = null }) {
    if (typeof prompt !== "string" || !prompt.trim()) throw new DesktopRuntimeError("CONVERSATION_REJECTED", "Prompt must not be empty");
    const catalog = await this.getAvailableModels({ signal });
    const model = resolveDesktopModel(catalog.models, requestedModel);
    const effort = resolveThinkingEffort(model, thinkingEffort);
    const appAttestChallenge = await this.prepareIntegrity({ signal });
    const parentMessageId = continuation?.parent_message_id || crypto.randomUUID();
    const messageId = crypto.randomUUID();
    const body = {
      action: "next",
      messages: [{
        id: messageId,
        author: { role: "user" },
        create_time: Math.floor(Date.now() / 1000),
        content: { content_type: "text", parts: [prompt] },
        metadata: {},
      }],
      model: model.id,
      parent_message_id: parentMessageId,
      timezone_offset_min: new Date().getTimezoneOffset(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      supported_encodings: ["v1"],
      local_function_signatures: [],
      app_attest_challenge: appAttestChallenge,
    };
    if (effort) body.thinking_effort = effort;
    if (continuation?.conversation_id) body.conversation_id = continuation.conversation_id;
    const events = await this.bridge.stream({
      method: "POST",
      url: "/f/conversation",
      body: JSON.stringify(body),
      signal,
      errorCode: "CONVERSATION_REJECTED",
    });
    const decoder = new DeltaDecoder();
    for await (const event of events) decoder.consume(event);
    const result = decoder.result({ transportComplete: true });
    return {
      ...result,
      model_id: model.id,
      requested_thinking_effort: thinkingEffort,
      observed_thinking_effort: effort,
      tools_enabled: false,
      local_function_signatures_count: body.local_function_signatures.length,
    };
  }
}

module.exports = { ChatGptDesktopConversationClient };
