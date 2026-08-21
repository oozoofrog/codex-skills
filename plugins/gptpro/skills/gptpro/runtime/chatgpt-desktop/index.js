"use strict";

const { discoverTarget, CdpClient, DEFAULT_ENDPOINT, DEFAULT_TARGET_URL } = require("./cdp-client");
const { DesktopBridge } = require("./desktop-bridge");
const { ChatGptDesktopConversationClient } = require("./conversation-client");
const { DesktopRuntimeError } = require("./errors");

function assertRendererIdentity(rendererUrl) {
  if (rendererUrl !== DEFAULT_TARGET_URL) {
    throw new DesktopRuntimeError("TARGET_NOT_FOUND", `Connected renderer is not ${DEFAULT_TARGET_URL}`);
  }
}

async function connectDesktopRuntime({ endpoint = DEFAULT_ENDPOINT, targetUrl = DEFAULT_TARGET_URL, fetchImpl, webSocketFactory, timeoutMs, signal } = {}) {
  if (targetUrl !== DEFAULT_TARGET_URL) {
    throw new DesktopRuntimeError("TARGET_NOT_FOUND", `Phase 1 requires the exact renderer target ${DEFAULT_TARGET_URL}`);
  }
  const discovered = await discoverTarget({ endpoint, targetUrl, fetchImpl, signal });
  const cdp = new CdpClient(discovered.webSocketUrl, { webSocketFactory, commandTimeoutMs: Math.min(timeoutMs || 10000, 30000) });
  try {
    await cdp.connect(signal);
    const rendererUrl = await cdp.evaluate("window.location.href");
    if (signal?.aborted) throw signal.reason;
    assertRendererIdentity(rendererUrl);
    const bridge = new DesktopBridge(cdp, { timeoutMs });
    await bridge.initialize();
    const capabilities = await bridge.capabilities();
    return {
      endpoint: discovered.endpoint,
      targetUrl,
      targetId: discovered.target.id || null,
      capabilities,
      bridge,
      conversation: new ChatGptDesktopConversationClient(bridge),
      close() { bridge.close(); cdp.close(); },
    };
  } catch (error) {
    cdp.close();
    throw error;
  }
}

module.exports = { assertRendererIdentity, connectDesktopRuntime };
