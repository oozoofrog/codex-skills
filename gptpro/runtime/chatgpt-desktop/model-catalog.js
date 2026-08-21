"use strict";

const { DesktopRuntimeError } = require("./errors");

function uniqueStrings(values) {
  return [...new Set(values.filter((value) => typeof value === "string" && value.length))];
}

function displayName(raw, category, preset, slug) {
  return [
    preset?.title,
    category?.title,
    category?.human_category_short_name,
    category?.human_category_name,
    raw?.title,
    slug,
  ].find((value) => typeof value === "string" && value.length) || slug;
}

function normalizeDesktopCatalog(payload) {
  if (!payload || !Array.isArray(payload.models)) {
    throw new DesktopRuntimeError("MODEL_CATALOG_FAILED", "Desktop model catalog has no models array");
  }
  const rawModels = new Map();
  for (const model of payload.models) {
    if (!model || typeof model.slug !== "string" || !model.slug) {
      throw new DesktopRuntimeError("MODEL_CATALOG_FAILED", "Desktop model catalog contains an invalid model");
    }
    rawModels.set(model.slug, model);
  }
  const categories = (Array.isArray(payload.categories) ? payload.categories : [])
    .filter((category) => category && category.disabled_by_admin !== true);
  const versions = (Array.isArray(payload.versions) ? payload.versions : [])
    .filter((version) => version && version.disabled !== true);
  const autoCategory = categories.find((category) => category.model_lane === "auto");
  const presetOptions = (version) => {
    const presets = [];
    for (const preset of Array.isArray(version.intelligence_presets) ? version.intelligence_presets : []) {
      if (!preset || typeof preset.model_slug !== "string") continue;
      let slug = preset.model_slug;
      if (preset.lane === "instant" && typeof autoCategory?.default_model === "string" &&
          Array.isArray(version.slugs) && version.slugs.includes(autoCategory.default_model)) {
        slug = autoCategory.default_model;
      }
      const raw = rawModels.get(slug);
      if (!raw) continue;
      const category = categories.find((entry) => entry.default_model === slug ||
        (Array.isArray(entry.supported_models) && entry.supported_models.includes(slug)));
      presets.push({ slug, raw, category, preset, thinking_effort: preset.thinking_effort, version_id: version.id || null });
    }
    return presets;
  };
  const categoryOptions = (version = null) => {
    const versionSlugs = Array.isArray(version?.slugs) ? version.slugs : null;
    const result = [];
    for (const category of [...categories].reverse()) {
      const slug = [category.default_model, ...(Array.isArray(category.supported_models) ? category.supported_models : [])]
        .find((candidate) => typeof candidate === "string" && rawModels.has(candidate) && (!versionSlugs || versionSlugs.includes(candidate)));
      if (slug) result.push({ slug, raw: rawModels.get(slug), category, preset: null, thinking_effort: null, version_id: version?.id || null });
    }
    return result;
  };
  let topOptions = [];
  const allVersionOptions = [];
  for (const version of versions) {
    const presets = presetOptions(version);
    if (!topOptions.length && presets.length) topOptions = presets;
    const expanded = presets.length ? presets : categoryOptions(version);
    allVersionOptions.push(...expanded);
  }
  if (!topOptions.length) topOptions = categoryOptions();
  const options = [...topOptions, ...allVersionOptions];
  if (!options.length) {
    throw new DesktopRuntimeError("MODEL_CATALOG_FAILED", "Desktop catalog contains metadata but no selectable public model options");
  }
  const sliderEfforts = new Map();
  for (const entry of Array.isArray(payload.slider_settings) ? payload.slider_settings : []) {
    if (!entry || typeof entry.model_slug !== "string") continue;
    const current = sliderEfforts.get(entry.model_slug) || [];
    current.push(entry.thinking_effort);
    sliderEfforts.set(entry.model_slug, current);
  }
  const grouped = new Map();
  for (const option of options) {
    const current = grouped.get(option.slug) || {
      id: option.slug,
      name: displayName(option.raw, option.category, option.preset, option.slug),
      efforts: [],
      defaultEffort: option.raw.default_thinking_effort,
      description: option.category?.short_explainer || option.raw.description || null,
      versions: new Set(),
    };
    current.efforts.push(option.raw.default_thinking_effort, ...(sliderEfforts.get(option.slug) || []), option.thinking_effort);
    if (option.version_id) current.versions.add(option.version_id);
    grouped.set(option.slug, current);
  }
  let models = [...grouped.values()].map((model) => {
    const efforts = uniqueStrings(model.efforts);
    return {
      id: model.id,
      name: model.name,
      reasoning: efforts.length > 0,
      thinking_efforts: efforts,
      context_window: 0,
      capabilities: {
        default_thinking_effort: typeof model.defaultEffort === "string" ? model.defaultEffort : null,
        description: typeof model.description === "string" ? model.description : null,
        version_ids: [...model.versions],
      },
    };
  });
  const policyPayload = payload.workspace_model_policy;
  const policySelection = policyPayload?.selection;
  const catalogDefault = models.find((model) => model.id === payload.default_model_slug) || models[0];
  let workspacePolicy = null;
  if (policyPayload && typeof policyPayload === "object") {
    const explicitPolicyModelId = typeof policySelection?.model === "string" ? policySelection.model : null;
    const effectivePolicyModelId = explicitPolicyModelId || catalogDefault.id;
    const policyModel = models.find((model) => model.id === effectivePolicyModelId) || null;
    const requestedPolicyEffort = policySelection?.thinking_effort ?? policySelection?.thinkingEffort ?? null;
    const policyEffort = policyModel && typeof requestedPolicyEffort === "string" && policyModel.thinking_efforts.includes(requestedPolicyEffort) ? requestedPolicyEffort : null;
    const precedence = typeof policyPayload.new_thread_precedence === "string" ? policyPayload.new_thread_precedence : null;
    workspacePolicy = {
      new_thread_precedence: precedence,
      model_id: policyModel?.id || null,
      thinking_effort: policyEffort,
      preferred_for_new_thread: precedence === "prefer_policy",
      resolved: policyModel !== null,
    };
  }
  return {
    source: "dynamic",
    catalog_scope: "selectable-public-options-and-versions",
    default_model_id: catalogDefault.id,
    workspace_policy: workspacePolicy,
    models,
  };
}

function resolveDesktopModel(models, requested) {
  const exactId = models.filter((model) => model.id === requested);
  if (exactId.length === 1) return exactId[0];
  const folded = String(requested).toLocaleLowerCase();
  const candidates = models.filter((model) =>
    model.id.toLocaleLowerCase() === folded || model.name.toLocaleLowerCase() === folded);
  if (!candidates.length) throw new DesktopRuntimeError("MODEL_NOT_FOUND", `Requested model is not in the live Desktop catalog: ${requested}`);
  if (candidates.length > 1) throw new DesktopRuntimeError("MODEL_AMBIGUOUS", `Requested model matches multiple live Desktop catalog entries: ${requested}`);
  return candidates[0];
}

function resolveThinkingEffort(model, requestedEffort) {
  if (requestedEffort == null) return model.capabilities.default_thinking_effort || null;
  if (!model.thinking_efforts.includes(requestedEffort)) {
    throw new DesktopRuntimeError("MODEL_EFFORT_UNSUPPORTED", `Thinking effort ${requestedEffort} is not supported by ${model.id}`);
  }
  return requestedEffort;
}

module.exports = { normalizeDesktopCatalog, resolveDesktopModel, resolveThinkingEffort };
