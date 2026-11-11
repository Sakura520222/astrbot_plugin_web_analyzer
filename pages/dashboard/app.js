const PLUGIN_NAME = "astrbot_plugin_web_analyzer";

const bridge = window.AstrBotPluginView || window.AstrBotPluginPage;

/* ========== i18n ========== */
function t(key, fallback) {
  const missing = "__web_analyzer_missing__";
  const preferred = bridge.t(`views.dashboard.${key}`, missing);
  return preferred === missing ? bridge.t(`pages.dashboard.${key}`, fallback) : preferred;
}

function applyPageContext(context) {
  if (typeof context?.isDark === "boolean") {
    document.documentElement.dataset.theme = context.isDark ? "dark" : "light";
  }
  document.documentElement.lang = context?.locale || "zh-CN";
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.dataset.fallbackText ??= element.textContent;
    element.textContent = t(element.dataset.i18n, element.dataset.fallbackText);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.dataset.fallbackPlaceholder ??= element.placeholder;
    element.placeholder = t(element.dataset.i18nPlaceholder, element.dataset.fallbackPlaceholder);
  });
  const activeLabel = document.querySelector(`.nav-item[data-page="${currentPage}"] .nav-text`);
  if (activeLabel) document.getElementById("page-title").textContent = activeLabel.textContent;
}

/* ========== State ========== */
let currentPage = "overview";

/* ========== Toast ========== */
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("toast-fade-out");
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

/* ========== Navigation ========== */
function initNavigation() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      const page = item.dataset.page;
      switchPage(page);
    });
  });
}

function switchPage(page) {
  if (page === currentPage) return;
  if (hasUnsavedConfig() && !window.confirm("配置有未保存的修改，确定离开此页面吗？")) return;
  currentPage = page;
  document.querySelectorAll(".nav-item").forEach((el) => {
    const active = el.dataset.page === page;
    el.classList.toggle("active", active);
    if (active) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("active"));
  document.getElementById(`page-${page}`).classList.add("active");
  document.getElementById("page-title").textContent = t(`nav.${page}`, { overview: "概览", cache: "缓存管理", domains: "域名管理", groups: "群聊管理", config: "配置编辑", browser: "浏览器状态" }[page] || page);

  loadPageData(page);
}

function hasUnsavedConfig() {
  return Boolean(document.querySelector("#config-content .config-field.modified"));
}

/* ========== Data Loading ========== */
async function loadPageData(page) {
  switch (page) {
    case "overview":
      await loadOverview();
      break;
    case "cache":
      await loadCache();
      break;
    case "domains":
      await loadDomains();
      break;
    case "groups":
      await loadGroups();
      break;
    case "config":
      await loadConfig();
      break;
    case "browser":
      await loadBrowserStatus();
      break;
  }
}

/* ========== Overview ========== */
async function loadOverview() {
  try {
    const data = await bridge.apiGet("dashboard/overview");
    document.getElementById("stat-cache-total").textContent = data.cache_stats.total;
    document.getElementById("stat-cache-valid").textContent = data.cache_stats.valid;
    document.getElementById("stat-cache-expired").textContent = data.cache_stats.expired;
    document.getElementById("stat-analysis-mode").textContent = data.analysis_mode;

    renderQuickStatus(data);
    renderFeatureStatus(data);
  } catch (e) {
    showToast("加载概览数据失败: " + e.message, "error");
  }
}

function modeLabel(value) {
  const labels = { auto: "自动分析", manual: "手动分析", hybrid: "混合模式", LLMTOOL: "模型工具", httpx: "HTTP 请求", browser: "系统浏览器" };
  return labels[value] || value || "—";
}

function renderQuickStatus(data) {
  const el = document.getElementById("quick-status");
  const items = [
    { label: t("overview.analysisMode", "分析模式"), value: modeLabel(data.analysis_mode), color: "blue" },
    { label: t("overview.autoAnalyze", "自动分析"), value: data.auto_analyze ? "已启用" : "已禁用", state: data.auto_analyze },
    { label: t("overview.llmEnabled", "模型分析"), value: data.llm_enabled ? "已启用" : "已禁用", state: data.llm_enabled },
    { label: t("overview.screenshotEnabled", "网页截图"), value: data.enable_screenshot ? "已启用" : "已禁用", state: data.enable_screenshot },
    { label: t("overview.fetchMode", "抓取模式"), value: modeLabel(data.fetch_mode), color: "blue" },
    { label: t("overview.concurrency", "最大并发"), value: data.max_concurrency, color: "blue" },
  ];
  el.innerHTML = items
    .map(
      (i) => `
    <div class="status-item">
      <span class="status-label">${escapeHtml(i.label)}</span>
      <span class="status-value ${i.state === undefined ? "" : i.state ? "state-enabled" : "state-disabled"}">${escapeHtml(String(i.value ?? ""))}</span>
    </div>`
    )
    .join("");
}

function renderFeatureStatus(data) {
  const el = document.getElementById("feature-status");
  const items = [
    { label: t("overview.cacheEnabled", "缓存"), value: data.enable_cache },
    { label: t("overview.translationEnabled", "翻译"), value: data.enable_translation },
    { label: t("overview.emojiEnabled", "结果表情符号"), value: data.enable_emoji },,
    { label: t("overview.statisticsEnabled", "统计"), value: data.enable_statistics },
    { label: t("overview.specificExtraction", "指定内容提取"), value: data.enable_specific_extraction },,
    { label: t("overview.llmDecision", "模型选择输出"), value: data.enable_llm_decision },,
    { label: t("overview.recallEnabled", "消息撤回"), value: data.enable_recall },
    { label: t("overview.memoryMonitor", "内存监控"), value: data.enable_memory_monitor },
  ];
  el.innerHTML = items
    .map(
      (i) => `
    <div class="status-item">
      <span class="status-label">${i.label}</span>
      <span class="status-value ${i.value ? "state-enabled" : "state-disabled"}">${i.value ? "已启用" : "已禁用"}</span>
    </div>`
    )
    .join("");
}

/* ========== Cache ========== */
async function loadCache() {
  try {
    const data = await bridge.apiGet("dashboard/cache");
    document.getElementById("cache-total").textContent = data.stats.total;
    document.getElementById("cache-valid").textContent = data.stats.valid;
    document.getElementById("cache-expired").textContent = data.stats.expired;
    renderCacheTable(data.items);
  } catch (e) {
    showToast("加载缓存数据失败: " + e.message, "error");
  }
}

function renderCacheTable(items) {
  const tbody = document.getElementById("cache-table-body");
  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t("cache.empty", "暂无缓存数据")}</td></tr>`;
    return;
  }
  tbody.innerHTML = items
    .map(
      (item, idx) => `
    <tr>
      <td>${idx + 1}</td>
      <td class="url-cell" title="${escapeAttr(item.url)}">${truncateUrl(item.url, 50)}</td>
      <td><span class="badge badge-${item.expired ? "warning" : "success"}">${item.expired ? "已过期" : "有效"}</span></td>
      <td>${item.has_screenshot ? "有" : "无"}</td>
      <td>${formatTime(item.timestamp)}</td>
      <td><button class="btn btn-sm btn-danger btn-delete-cache" data-url="${escapeAttr(item.url)}">删除</button></td>
    </tr>`
    )
    .join("");

  tbody.querySelectorAll(".btn-delete-cache").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.dataset.url;
      if (confirm(t("cache.confirmDelete", "确认删除此缓存？"))) {
        try {
          await bridge.apiPost("dashboard/cache/delete", { url });
          showToast(t("cache.deleted", "缓存已删除"), "success");
          loadCache();
        } catch (e) {
          showToast("删除失败: " + e.message, "error");
        }
      }
    });
  });
}

/* ========== Domains ========== */
async function loadDomains() {
  try {
    const data = await bridge.apiGet("dashboard/domains");
    document.getElementById("toggle-unified-domain").checked = data.enable_unified_domain;
    renderTagList("allowed-domains-list", data.allowed_domains, "allowed");
    renderTagList("blocked-domains-list", data.blocked_domains, "blocked");
  } catch (e) {
    showToast("加载域名数据失败: " + e.message, "error");
  }
}

function renderTagList(containerId, items, type) {
  const container = document.getElementById(containerId);
  if (!items || items.length === 0) {
    container.innerHTML = `<div class="empty-tag">${t("domains.empty", "暂无数据")}</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
    <span class="tag ${type === "blocked" ? "tag-danger" : "tag-success"}">
      ${escapeHtml(item)}
      <button class="btn btn-icon tag-remove" type="button" aria-label="移除 ${escapeAttr(item)}" data-type="${type}" data-value="${escapeAttr(item)}">×</button>
    </span>`
    )
    .join("");

  container.querySelectorAll(".tag-remove").forEach((el) => {
    el.addEventListener("click", async () => {
      try {
        await bridge.apiPost("dashboard/domains/remove", {
          type: el.dataset.type,
          value: el.dataset.value,
        });
        showToast(t("domains.removed", "已移除"), "success");
        loadDomains();
      } catch (e) {
        showToast("移除失败: " + e.message, "error");
      }
    });
  });
}

/* ========== Groups ========== */
async function loadGroups() {
  try {
    const data = await bridge.apiGet("dashboard/groups");
    renderGroupList(data.group_blacklist);
  } catch (e) {
    showToast("加载群聊数据失败: " + e.message, "error");
  }
}

function renderGroupList(items) {
  const container = document.getElementById("group-blacklist-list");
  if (!items || items.length === 0) {
    container.innerHTML = `<div class="empty-tag">${t("groups.empty", "黑名单为空")}</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
    <span class="tag tag-danger">
      ${escapeHtml(item)}
      <button class="btn btn-icon tag-remove" type="button" aria-label="移除 ${escapeAttr(item)}" data-group-id="${escapeAttr(item)}">×</button>
    </span>`
    )
    .join("");

  container.querySelectorAll(".tag-remove").forEach((el) => {
    el.addEventListener("click", async () => {
      try {
        await bridge.apiPost("dashboard/groups/remove", {
          group_id: el.dataset.groupId,
        });
        showToast(t("groups.removed", "已移除"), "success");
        loadGroups();
      } catch (e) {
        showToast("移除失败: " + e.message, "error");
      }
    });
  });
}

/* ========== Config ========== */
let configOriginalValues = {};

async function loadConfig() {
  try {
    const data = await bridge.apiGet("dashboard/config/schema");
    renderConfigForm(data.groups);
  } catch (e) {
    showToast("加载配置失败: " + e.message, "error");
  }
}

function renderConfigForm(groups) {
  configOriginalValues = {};
  const container = document.getElementById("config-content");

  const html = groups
    .map((group) => {
      const groupTitle = group.description || group.display_name || group.name;
      const sectionsHtml = group.sections
        .map((section) => renderConfigSection(section, group))
        .join("");
      return `
      <div class="config-group" data-group="${escapeAttr(group.name)}">
        <div class="config-group-header">
          <h3>${escapeHtml(groupTitle)}</h3>
          ${group.hint && group.hint !== groupTitle ? `<span class="config-group-hint">${escapeHtml(group.hint)}</span>` : ""}
        </div>
        ${sectionsHtml}
      </div>`;
    })
    .join("");

  container.innerHTML = html;

  // 绑定保存按钮事件
  container.querySelectorAll(".btn-save-section").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const section = btn.closest(".config-section");
      await saveConfigSection(section);
    });
  });

  // 绑定重置按钮事件
  container.querySelectorAll(".btn-reset-section").forEach((btn) => {
    btn.addEventListener("click", () => {
      const section = btn.closest(".config-section");
      if (section.querySelector(".config-field.modified") && !window.confirm("放弃此配置区未保存的修改？")) return;
      resetConfigSection(section);
    });
  });
}

function renderConfigSection(section, group) {
  const fieldsHtml = section.fields
    .map((field) => renderConfigField(field))
    .join("");
  const showHeading = section.name !== group.name && section.name !== group.description;

  return `
    <div class="config-section" data-section="${escapeAttr(section.name)}">
      ${showHeading ? `<div class="config-section-header"><h4 class="config-section-title">${escapeHtml(section.description || section.name)}</h4><div class="config-section-actions"><button class="btn btn-sm btn-reset-section" type="button" aria-label="重置 ${escapeAttr(section.description || section.name)}">重置</button><button class="btn btn-sm btn-primary btn-save-section" type="button" aria-label="保存 ${escapeAttr(section.description || section.name)}">保存</button></div></div>` : `<div class="config-section-actions config-section-actions-top"><button class="btn btn-sm btn-reset-section" type="button" aria-label="重置 ${escapeAttr(group.description || group.name)}">重置</button><button class="btn btn-sm btn-primary btn-save-section" type="button" aria-label="保存 ${escapeAttr(group.description || group.name)}">保存</button></div>`}
      ${section.hint && showHeading ? `<p class="config-section-desc">${escapeHtml(section.hint)}</p>` : ""}
      <div class="config-fields">${fieldsHtml}</div>
    </div>`;
}

function renderConfigField(field) {
  const inputHtml = buildFieldInput(field);
  // 保存原始值
  configOriginalValues[field.path] = field.value;

  return `
    <div class="config-field" data-field-path="${escapeAttr(field.path)}">
      <div class="config-field-header">
        <label class="config-field-label" for="cfg-${escapeAttr(field.path)}">${escapeHtml(field.label)}</label>
        ${field.secret ? '<span class="config-field-hint">敏感配置</span>' : ""}
      </div>
      ${field.hint ? `<p class="config-field-subtitle">${escapeHtml(field.hint)}</p>` : ""}
      ${field.subtitle ? `<p class="config-field-subtitle">${escapeHtml(field.subtitle)}</p>` : ""}
      ${inputHtml}
      ${field.secret ? `<label class="secret-clear"><input type="checkbox" data-clear-secret="${escapeAttr(field.path)}" aria-label="清除已保存的代理配置" ${field.has_value ? "" : "disabled"} />清除已保存的值</label><span class="secret-hint">${field.has_value ? "已配置。留空可保留原值，输入新值以替换。" : "尚未配置。输入值后保存。"}</span>` : ""}
    </div>`;
}

function buildFieldInput(field) {
  const path = field.path;
  const val = field.value;

  const labels = Array.isArray(field.labels) ? field.labels : [];
  if (field.options) {
    const options = field.options.map((option, index) =>
      typeof option === "object" && option !== null
        ? { value: option.value ?? option.id ?? option.name, label: option.label ?? option.title ?? option.name ?? labels[index] ?? option.value ?? option.id }
        : { value: option, label: labels[index] ?? option }
    );
    const opts = options
      .map((option) => `<option value="${escapeAttr(String(option.value))}" ${String(option.value) === String(val) ? "selected" : ""}>${escapeHtml(String(option.label))}</option>`)
      .join("");
    return `<select id="cfg-${escapeAttr(path)}" class="config-input config-select" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val ?? ""))}">${opts}</select>`;
  }

  if (field.type === "bool") {
    return `
      <div class="config-toggle">
        <label>
          <input id="cfg-${escapeAttr(path)}" type="checkbox" class="config-checkbox" data-path="${escapeAttr(path)}" data-original="${val ? "true" : "false"}" ${val ? "checked" : ""} />
          <span class="toggle-slider"></span>
          <span class="config-toggle-label">${val ? "已启用" : "已禁用"}</span>
        </label>
      </div>`;
  }

  if (field.type === "select_provider" || field.type === "provider") {
    const options = Array.isArray(field.providers) ? field.providers : Array.isArray(field.options) ? field.options : [];
    if (options.length) {
      const items = options.map((option) => typeof option === "object" && option !== null
        ? { value: option.value ?? option.id ?? option.name, label: option.label ?? option.name ?? option.value ?? option.id }
        : { value: option, label: option });
      return `<select id="cfg-${escapeAttr(path)}" class="config-input config-select" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val ?? ""))}">${items.map((option) => `<option value="${escapeAttr(String(option.value))}" ${String(option.value) === String(val) ? "selected" : ""}>${escapeHtml(String(option.label))}</option>`).join("")}</select>`;
    }
  }

  if (field.type === "text") {
    return `<textarea id="cfg-${escapeAttr(path)}" class="config-input config-textarea" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val))}" rows="3">${escapeHtml(String(val))}</textarea>`;
  }

  if (field.secret) {
    return `<input id="cfg-${escapeAttr(path)}" type="password" class="config-input" data-path="${escapeAttr(path)}" data-secret="true" data-has-value="${field.has_value ? "true" : "false"}" data-original="" value="" placeholder="${field.has_value ? "已配置，输入以替换" : "尚未配置"}" autocomplete="new-password" />`;
  }
  if (field.type === "int" || field.type === "float") {
    const step = field.type === "float" ? "0.1" : "1";
    const min = field.minimum !== undefined ? `min="${field.minimum}"` : "";
    const max = field.maximum !== undefined ? `max="${field.maximum}"` : "";
    return `<input id="cfg-${escapeAttr(path)}" type="number" class="config-input" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val))}" value="${escapeAttr(String(val))}" step="${step}" ${min} ${max} />`;
  }

  return `<input id="cfg-${escapeAttr(path)}" type="${field.secret ? "password" : "text"}" class="config-input" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val ?? ""))}" value="${escapeAttr(String(val ?? ""))}" autocomplete="${field.secret ? "new-password" : "off"}" />`;
}

async function saveConfigSection(sectionEl) {
  if (sectionEl.dataset.saving === "true") return;
  let updates;
  try {
    updates = collectSectionChanges(sectionEl);
  } catch (error) {
    showToast(error.message, "error");
    return;
  }
  if (Object.keys(updates).length === 0) {
    showToast("没有修改的配置项", "info");
    return;
  }

  sectionEl.dataset.saving = "true";
  const buttons = sectionEl.querySelectorAll(".btn-save-section, .btn-reset-section");
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const result = await bridge.apiPost("dashboard/config/update", { updates });
    showToast(result.message, result.errors && result.errors.length > 0 ? "error" : "success");

    const errors = result.errors || [];
    const appliedPaths = new Set(result.applied_paths || (errors.length ? [] : Object.keys(updates)));
    const failedPaths = new Set(errors.map((error) => typeof error === "object" ? error.path : null).filter(Boolean));
    const hasUnmappedError = errors.length > 0 && failedPaths.size === 0;
    if (!hasUnmappedError) {
      for (const [path] of Object.entries(updates)) {
        if (failedPaths.has(path) || !appliedPaths.has(path)) continue;
        const input = sectionEl.querySelector(`.config-input[data-path="${CSS.escape(path)}"], .config-checkbox[data-path="${CSS.escape(path)}"]`);
        if (!input) continue;
        if (input.dataset.secret === "true") {
          const clearControl = sectionEl.querySelector(`[data-clear-secret="${CSS.escape(path)}"]`);
          const submittedValue = updates[path];
          const submittedClear = submittedValue === "";
          input.dataset.hasValue = submittedClear ? "false" : "true";
          input.placeholder = submittedClear ? "尚未配置" : "已配置，输入以替换";
          if (clearControl) clearControl.disabled = submittedClear;
          const hint = input.closest(".config-field")?.querySelector(".secret-hint");
          if (hint) hint.textContent = submittedClear ? "尚未配置。输入值后保存。" : "已配置。留空可保留原值，输入新值以替换。";
          if (input.value === submittedValue) input.value = "";
          if (clearControl?.checked && submittedClear) clearControl.checked = false;
          const secretStillDirty = input.value !== "" || Boolean(clearControl?.checked);
          input.closest(".config-field")?.classList.toggle("modified", secretStillDirty);
          continue;
        }
        const submittedValue = updates[path];
        input.dataset.original = String(submittedValue);
        configOriginalValues[path] = submittedValue;
        const currentValue = input.type === "checkbox" ? String(input.checked) : input.value;
        input.closest(".config-field")?.classList.toggle("modified", currentValue !== input.dataset.original);
      }
    }
  } catch (e) {
    showToast("保存失败: " + e.message, "error");
  } finally {
    sectionEl.dataset.saving = "false";
    buttons.forEach((button) => { button.disabled = false; });
  }
}

function collectSectionChanges(sectionEl) {
  const updates = {};
  sectionEl.querySelectorAll(".config-input[data-path], .config-checkbox[data-path]").forEach((input) => {
    const path = input.dataset.path;
    if (input.dataset.secret === "true") {
      const clearControl = sectionEl.querySelector(`[data-clear-secret="${CSS.escape(path)}"]`);
      if (clearControl?.checked) input.closest(".config-field")?.classList.add("modified");
      else if (input.value !== "") input.closest(".config-field")?.classList.add("modified");
      else input.closest(".config-field")?.classList.remove("modified");
      if (clearControl?.checked) updates[path] = "";
      else if (input.value !== "") updates[path] = input.value;
      return;
    }
    let currentValue;
    if (input.type === "checkbox") {
      currentValue = input.checked;
    } else if (input.tagName === "SELECT") {
      currentValue = input.value;
    } else if (input.type === "number") {
      if (input.value.trim() === "" || !input.checkValidity()) {
        input.reportValidity();
        throw new Error("请填写范围内的有效数字");
      }
      currentValue = Number(input.value);
    } else {
      currentValue = input.value;
    }
    const original = input.dataset.original;

    // 比较值是否改变
    const changed = String(currentValue) !== String(original);
    const fieldEl = input.closest(".config-field");

    if (changed) {
      updates[path] = currentValue;
      if (fieldEl) fieldEl.classList.add("modified");
    } else {
      if (fieldEl) fieldEl.classList.remove("modified");
    }
  });
  return updates;
}

function resetConfigSection(sectionEl) {
  sectionEl.querySelectorAll(".config-input[data-path], .config-checkbox[data-path]").forEach((input) => {
    const original = input.dataset.original;
    if (input.dataset.secret === "true") {
      input.value = "";
      input.placeholder = input.dataset.hasValue === "true" ? "已配置，输入以替换" : "尚未配置";
      const clearControl = sectionEl.querySelector(`[data-clear-secret="${CSS.escape(input.dataset.path)}"]`);
      if (clearControl) clearControl.checked = false;
    } else if (input.type === "checkbox") {
      input.checked = original === "true";
      const label = input.closest(".config-toggle").querySelector(".config-toggle-label");
      if (label) label.textContent = input.checked ? "已启用" : "已禁用";
    } else {
      input.value = original;
    }
    input.closest(".config-field")?.classList.remove("modified");
  });
  showToast("已重置为上次保存的值", "info");
}


/* ========== Browser ========== */
async function loadBrowserStatus() {
  try {
    const data = await bridge.apiGet("dashboard/browser");
    renderBrowserStatus(data);
  } catch (e) {
    showToast("加载浏览器状态失败: " + e.message, "error");
  }
}

function renderBrowserStatus(data) {
  const el = document.getElementById("browser-status");
  const rows = [
    { label: t("browser.installed", "浏览器状态"), value: data.installed ? "已检测到系统浏览器" : "未检测到系统浏览器", state: data.installed },
    { label: t("browser.type", "浏览器类型"), value: data.browser_type || "—" },
    { label: t("browser.path", "浏览器路径"), value: data.install_path || "—" },
    { label: t("browser.version", "浏览器版本"), value: data.browser_version || "—" },
    { label: t("browser.dirSize", "旧版 Playwright 残留"), value: data.install_dir_exists ? `${data.install_dir_size_mb} MB` : "—" },
    { label: t("browser.poolSize", "实例池"), value: `${data.browser_pool_size} 个实例` },
  ];
  el.innerHTML = rows
    .map(
      (r) => `
    <div class="status-item">
      <span class="status-label">${escapeHtml(r.label)}</span>
      <span class="status-value ${r.state === undefined ? "" : r.state ? "state-enabled" : "state-disabled"}">${escapeHtml(String(r.value ?? ""))}</span>
    </div>`
    )
    .join("");
}

/* ========== Utilities ========== */
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function escapeAttr(str) {
  return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function truncateUrl(url, maxLen) {
  if (url.length <= maxLen) return escapeHtml(url);
  return escapeHtml(url.substring(0, maxLen - 3) + "...");
}

function formatTime(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/* ========== Event Bindings ========== */
function initEvents() {
  // Refresh
  document.getElementById("btn-refresh").addEventListener("click", () => {
    if (hasUnsavedConfig() && !window.confirm("配置有未保存的修改，确定重新加载吗？")) return;
    loadPageData(currentPage);
  });

  window.addEventListener("beforeunload", (event) => {
    if (!hasUnsavedConfig()) return;
    event.preventDefault();
    event.returnValue = "";
  });

  // Cache: clear all
  document.getElementById("card-clear-cache").addEventListener("click", async () => {
    if (confirm(t("cache.confirmClear", "确认清空所有缓存？此操作不可恢复"))) {
      try {
        const result = await bridge.apiPost("dashboard/cache/clear");
        showToast(result.message, "success");
        loadCache();
      } catch (e) {
        showToast("清空缓存失败: " + e.message, "error");
      }
    }
  });

  // Cache: search
  document.getElementById("cache-search").addEventListener("input", (e) => {
    const keyword = e.target.value.toLowerCase();
    document.querySelectorAll("#cache-table-body tr").forEach((row) => {
      const urlCell = row.querySelector(".url-cell");
      if (urlCell) {
        row.style.display = urlCell.textContent.toLowerCase().includes(keyword) ? "" : "none";
      }
    });
  });

  // Domains: add allowed
  document.getElementById("btn-add-allowed").addEventListener("click", async () => {
    const input = document.getElementById("input-allowed-domain");
    const value = input.value.trim();
    if (!value) return;
    try {
      await bridge.apiPost("dashboard/domains/add", { type: "allowed", value });
      input.value = "";
      showToast(t("domains.added", "已添加"), "success");
      loadDomains();
    } catch (e) {
      showToast("添加失败: " + e.message, "error");
    }
  });

  // Domains: add blocked
  document.getElementById("btn-add-blocked").addEventListener("click", async () => {
    const input = document.getElementById("input-blocked-domain");
    const value = input.value.trim();
    if (!value) return;
    try {
      await bridge.apiPost("dashboard/domains/add", { type: "blocked", value });
      input.value = "";
      showToast(t("domains.added", "已添加"), "success");
      loadDomains();
    } catch (e) {
      showToast("添加失败: " + e.message, "error");
    }
  });

  // Domains: toggle unified
  document.getElementById("toggle-unified-domain").addEventListener("change", async (e) => {
    try {
      await bridge.apiPost("dashboard/domains/toggle_unified", {
        enabled: e.target.checked,
      });
      showToast(t("domains.updated", "已更新"), "success");
    } catch (err) {
      showToast("更新失败: " + err.message, "error");
      e.target.checked = !e.target.checked;
    }
  });

  // Groups: add
  document.getElementById("btn-add-group").addEventListener("click", async () => {
    const input = document.getElementById("input-group-id");
    const value = input.value.trim();
    if (!value) return;
    try {
      await bridge.apiPost("dashboard/groups/add", { group_id: value });
      input.value = "";
      showToast(t("groups.added", "已添加"), "success");
      loadGroups();
    } catch (e) {
      showToast("添加失败: " + e.message, "error");
    }
  });

  // Enter key for inputs
  ["input-allowed-domain", "input-blocked-domain", "input-group-id"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.target.closest(".card").querySelector("button.btn").click();
      }
    });
  });

  // Browser: refresh
  document.getElementById("btn-refresh-browser").addEventListener("click", () => {
    loadBrowserStatus();
  });

  // Browser: uninstall (清理旧版 Playwright 残留文件)
  document.getElementById("btn-uninstall-browser").addEventListener("click", async () => {
    if (confirm(t("browser.confirmUninstall", "确认清理旧版 Playwright 浏览器残留文件？当前版本使用系统浏览器，不受影响"))) {
      try {
        const result = await bridge.apiPost("dashboard/browser/uninstall");
        showToast(result.message, "success");
        loadBrowserStatus();
      } catch (e) {
        showToast("清理失败: " + e.message, "error");
      }
    }
  });

  document.getElementById("config-content").addEventListener("input", updateConfigFieldState);
  document.getElementById("config-content").addEventListener("change", (e) => {
    if (e.target.matches("[data-clear-secret]")) {
      const field = e.target.closest(".config-field");
      field?.classList.toggle("modified", e.target.checked || field.querySelector('[data-secret="true"]')?.value !== "");
      return;
    }
    if (e.target.classList.contains("config-checkbox")) {
      const label = e.target.closest(".config-toggle")?.querySelector(".config-toggle-label");
      if (label) label.textContent = e.target.checked ? "已启用" : "已禁用";
    }
    updateConfigFieldState(e);
  });
}

function updateConfigFieldState(event) {
  const input = event.target.closest("[data-path]");
  if (!input) return;
  if (input.dataset.secret === "true") {
    const clearControl = document.querySelector(`[data-clear-secret="${CSS.escape(input.dataset.path)}"]`);
    input.closest(".config-field")?.classList.toggle("modified", input.value !== "" || Boolean(clearControl?.checked));
    return;
  }
  const value = input.type === "checkbox" ? String(input.checked) : input.value;
  input.closest(".config-field")?.classList.toggle("modified", value !== input.dataset.original);
}

/* ========== Init ========== */
async function init() {
  try {
    await bridge.ready();
    const context = bridge.getContext?.();
    applyPageContext(context);
    const unsubscribe = bridge.onContext?.(applyPageContext);
    window.addEventListener("pagehide", () => unsubscribe?.(), { once: true });
    initNavigation();
    initEvents();
    loadPageData("overview");
  } catch (e) {
    console.error("Dashboard init failed:", e);
  }
}

init();
