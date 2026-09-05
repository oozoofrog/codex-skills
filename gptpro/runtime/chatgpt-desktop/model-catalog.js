"use strict";

const { runtimeError } = require("./errors.js");

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function text(...values) {
  const found = values.find((value) => typeof value === "string" && value.trim());
  return found?.trim();
}

function slugForPreset(preset) {
  return text(preset?.model_slug, preset?.modelSlug, typeof preset?.model === "string" ? preset.model : undefined, preset?.model?.slug, preset?.slug);
}

function effortForPreset(preset) {
  return text(preset?.thinking_effort, preset?.thinkingEffort, preset?.reasoning_effort, preset?.reasoningEffort, preset?.effort);
}

function effortValues(model) {
  const result = [];
  for (const item of Array.isArray(model?.thinking_efforts) ? model.thinking_efforts : []) {
    const value = typeof item === "string" ? item : text(item?.thinking_effort, item?.value, item?.id, item?.slug, item?.effort);
    if (value && !result.includes(value)) result.push(value);
  }
  return result;
}

function normalizeCatalog(catalog) {
  if (!object(catalog)) throw runtimeError("MODEL_CATALOG_FAILED", "The logged-in Desktop model catalog is invalid.");
  const records = new Map();
  for (const model of Array.isArray(catalog.models) ? catalog.models : []) {
    const id = text(model?.slug, model?.id);
    if (id) records.set(id, model);
  }
  const disabled = new Set();
  for (const category of Array.isArray(catalog.categories) ? catalog.categories : []) {
    if (!object(category) || category.disabled_by_admin !== true) continue;
    for (const id of Array.isArray(category.supported_models) ? category.supported_models : []) {
      if (typeof id === "string") disabled.add(id);
    }
  }
  const selectable = new Map();
  let versionPresetCount = 0;
  for (const version of Array.isArray(catalog.versions) ? catalog.versions : []) {
    if (!object(version) || version.disabled === true) continue;
    const presets = Array.isArray(version.intelligence_presets) ? version.intelligence_presets :
      Array.isArray(version.intelligencePresets) ? version.intelligencePresets : [];
    for (const preset of presets) {
      const id = slugForPreset(preset);
      if (!id || !records.has(id) || disabled.has(id)) continue;
      versionPresetCount += 1;
      if (!selectable.has(id)) selectable.set(id, new Set());
      const effort = effortForPreset(preset);
      if (effort) selectable.get(id).add(effort);
    }
  }
  for (const category of Array.isArray(catalog.categories) ? catalog.categories : []) {
    if (!object(category) || category.disabled_by_admin === true) continue;
    for (const id of Array.isArray(category.supported_models) ? category.supported_models : []) {
      if (typeof id === "string" && records.has(id) && !disabled.has(id) && !selectable.has(id)) selectable.set(id, new Set());
    }
  }
  const defaultId = text(catalog.default_model_slug);
  if (defaultId && records.has(defaultId) && !disabled.has(defaultId) && !selectable.has(defaultId)) selectable.set(defaultId, new Set());
  const models = [];
  for (const [id, presetEfforts] of selectable) {
    const model = records.get(id);
    const efforts = [...presetEfforts];
    if (!efforts.length && model?.configurable_thinking_effort === true) efforts.push(...effortValues(model));
    const context = Number(model?.max_tokens ?? model?.context_window ?? 0);
    const enabledTools = Array.isArray(model?.enabled_tools)
      ? model.enabled_tools.filter((value) => typeof value === "string")
      : [];
    models.push({
      id,
      name: text(model?.title, model?.name) ?? id,
      reasoning: efforts.length > 0 || model?.reasoning_type === "reasoning",
      thinking_efforts: [...new Set(efforts)],
      context_window: Number.isFinite(context) && context > 0 ? Math.trunc(context) : 0,
      default: id === defaultId,
      capabilities: {
        server_tools: enabledTools.length > 0,
        work_mode: model?.is_work_mode_model === true,
      },
    });
  }
  models.sort((a, b) => Number(b.default) - Number(a.default) || a.name.localeCompare(b.name));
  if (!models.length) throw runtimeError("MODEL_CATALOG_FAILED", "The logged-in Desktop catalog contains no selectable models.");
  return { source: "dynamic", models };
}

function resolveModel(catalog, intent, requestedEffort) {
  const models = Array.isArray(catalog?.models) ? catalog.models : [];
  if (!models.length) throw runtimeError("MODEL_CATALOG_FAILED", "No dynamic model catalog is available.");
  const requested = String(intent ?? "").trim();
  const candidates = models.filter((item) => item.id === requested);
  if (!candidates.length) throw runtimeError("MODEL_NOT_FOUND", `The exact Desktop model ID ${JSON.stringify(requested)} is unavailable.`);
  if (candidates.length !== 1) {
    throw runtimeError("MODEL_AMBIGUOUS", `The exact Desktop model ID ${JSON.stringify(requested)} appears more than once.`);
  }
  const model = candidates[0];
  if (requestedEffort) {
    if (!model.thinking_efforts.includes(requestedEffort)) {
      throw runtimeError("MODEL_EFFORT_UNSUPPORTED", `${model.name} does not advertise thinking effort ${requestedEffort}.`);
    }
  }
  return { ...model, thinking_effort: requestedEffort || undefined };
}

module.exports = { normalizeCatalog, resolveModel };
