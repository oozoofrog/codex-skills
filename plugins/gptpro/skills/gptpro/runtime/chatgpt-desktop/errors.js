"use strict";

class DesktopRuntimeError extends Error {
  constructor(code, message, options = {}) {
    super(message, options);
    this.name = "DesktopRuntimeError";
    this.code = code;
  }
}

function asRuntimeError(error, fallbackCode = "DESKTOP_CAPABILITY_UNAVAILABLE") {
  if (error instanceof DesktopRuntimeError) return error;
  return new DesktopRuntimeError(fallbackCode, "Unexpected ChatGPT Desktop runtime failure");
}

function errorPayload(error) {
  const normalized = asRuntimeError(error);
  return { ok: false, error: { code: normalized.code, message: normalized.message } };
}

module.exports = { DesktopRuntimeError, asRuntimeError, errorPayload };
