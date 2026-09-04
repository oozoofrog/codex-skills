"use strict";

class DesktopRuntimeError extends Error {
  constructor(code, message, options = {}) {
    super(message, options.cause ? { cause: options.cause } : undefined);
    this.name = "DesktopRuntimeError";
    this.code = code;
    this.retryable = options.retryable === true;
    this.recovery = options.recovery ?? "Run desktop-doctor and correct the reported capability before retrying.";
    this.submissionState = options.submissionState ?? "not_started";
    this.stage = typeof options.stage === "string" ? options.stage : null;
  }
}

function runtimeError(code, message, options) {
  return new DesktopRuntimeError(code, message, options);
}

function sanitizedError(error, fallbackCode = "DESKTOP_RUNTIME_ERROR") {
  if (error instanceof DesktopRuntimeError) {
    return {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      recovery: error.recovery,
      submission_state: error.submissionState,
      stage: error.stage,
      sanitized: true,
    };
  }
  return {
    code: fallbackCode,
    message: "The ChatGPT Desktop private runtime failed unexpectedly.",
    retryable: false,
    recovery: "Run desktop-doctor. Do not resend an ambiguous consultation.",
    submission_state: "unknown",
    sanitized: true,
  };
}

module.exports = { DesktopRuntimeError, runtimeError, sanitizedError };
