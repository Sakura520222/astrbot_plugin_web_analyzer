const PLUGIN_NAME = "astrbot_plugin_web_analyzer";

const bridge = window.AstrBotPluginPage;

/* ========== i18n ========== */
function t(key, fallback) {
  return bridge.t(`pages.dashboard.${key}`, fallback);
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
  currentPage = page;
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
  document.querySelector(`.nav-item[data-page="${page}"]`).classList.add("active");
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("active"));
  document.getElementById(`page-${page}`).classList.add("active");
  document.getElementById("page-title").textContent = t(`nav.${page}`, page);

  loadPageData(page);
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

function renderQuickStatus(data) {
  const el = document.getElementById("quick-status");
  const items = [
    { label: t("overview.analysisMode", "分析模式"), value: data.analysis_mode, color: "blue" },
    { label: t("overview.autoAnalyze", "自动分析"), value: data.auto_analyze ? "✅" : "❌", color: "" },
    { label: t("overview.llmEnabled", "LLM 分析"), value: data.llm_enabled ? "✅" : "❌", color: "" },
    { label: t("overview.screenshotEnabled", "网页截图"), value: data.enable_screenshot ? "✅" : "❌", color: "" },
    { label: t("overview.fetchMode", "抓取模式"), value: data.fetch_mode, color: "blue" },
    { label: t("overview.concurrency", "最大并发"), value: data.max_concurrency, color: "blue" },
  ];
  el.innerHTML = items
    .map(
      (i) => `
    <div class="status-item">
      <span class="status-label">${i.label}</span>
      <span class="status-value ${i.color ? "text-" + i.color : ""}">${i.value}</span>
    </div>`
    )
    .join("");
}

function renderFeatureStatus(data) {
  const el = document.getElementById("feature-status");
  const items = [
    { label: t("overview.cacheEnabled", "缓存"), value: data.enable_cache },
    { label: t("overview.translationEnabled", "翻译"), value: data.enable_translation },
    { label: t("overview.emojiEnabled", "Emoji"), value: data.enable_emoji },
    { label: t("overview.statisticsEnabled", "统计"), value: data.enable_statistics },
    { label: t("overview.specificExtraction", "特定提取"), value: data.enable_specific_extraction },
    { label: t("overview.llmDecision", "LLM决策"), value: data.enable_llm_decision },
    { label: t("overview.recallEnabled", "消息撤回"), value: data.enable_recall },
    { label: t("overview.memoryMonitor", "内存监控"), value: data.enable_memory_monitor },
  ];
  el.innerHTML = items
    .map(
      (i) => `
    <div class="status-item">
      <span class="status-label">${i.label}</span>
      <span class="status-value">${i.value ? "✅" : "❌"}</span>
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
      <td>${item.has_screenshot ? "📷" : "—"}</td>
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
      <span class="tag-remove" data-type="${type}" data-value="${escapeAttr(item)}">&times;</span>
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
      <span class="tag-remove" data-group-id="${escapeAttr(item)}">&times;</span>
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
      const sectionsHtml = group.sections
        .map((section) => renderConfigSection(section))
        .join("");
      return `
      <div class="config-group" data-group="${escapeAttr(group.name)}">
        <div class="config-group-header">
          <h3>${escapeHtml(group.name)}</h3>
          <span class="config-group-hint">${escapeHtml(group.hint || group.description || "")}</span>
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
      resetConfigSection(section);
    });
  });
}

function renderConfigSection(section) {
  const fieldsHtml = section.fields
    .map((field) => renderConfigField(field))
    .join("");

  return `
    <div class="config-section" data-section="${escapeAttr(section.name)}">
      <div class="config-section-header">
        <h4 class="config-section-title">${escapeHtml(section.name)}</h4>
        <div class="config-section-actions">
          <button class="btn btn-sm btn-reset-section">重置</button>
          <button class="btn btn-sm btn-primary btn-save-section">保存</button>
        </div>
      </div>
      ${section.description ? `<p class="config-section-desc">${escapeHtml(section.description)}</p>` : ""}
      <div class="config-fields">${fieldsHtml}</div>
    </div>`;
}

function renderConfigField(field) {
  const inputHtml = buildFieldInput(field);
  // 保存原始值
  configOriginalValues[field.path] = field.value;

  return `
    <div class="config-field" data-path="${escapeAttr(field.path)}">
      <div class="config-field-header">
        <label class="config-field-label" for="cfg-${escapeAttr(field.path)}">${escapeHtml(field.label)}</label>
        ${field.hint ? `<span class="config-field-hint" title="${escapeHtml(field.hint)}">ℹ️</span>` : ""}
      </div>
      ${inputHtml}
    </div>`;
}

function buildFieldInput(field) {
  const path = field.path;
  const val = field.value;

  // 带选项的下拉选择
  if (field.options) {
    const opts = field.options
      .map(
        (o) =>
          `<option value="${escapeHtml(o)}" ${o === val ? "selected" : ""}>${escapeHtml(o)}</option>`
      )
      .join("");
    return `<select class="config-input config-select" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val))}">${opts}</select>`;
  }

  // 布尔开关
  if (field.type === "bool") {
    return `
      <div class="config-toggle">
        <label>
          <input type="checkbox" class="config-checkbox" data-path="${escapeAttr(path)}" data-original="${val ? "true" : "false"}" ${val ? "checked" : ""} />
          <span class="toggle-slider"></span>
          <span class="config-toggle-label">${val ? "已启用" : "已禁用"}</span>
        </label>
      </div>`;
  }

  // 多行文本
  if (field.type === "text") {
    return `<textarea class="config-input config-textarea" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val))}" rows="3">${escapeHtml(String(val))}</textarea>`;
  }

  // 数值输入
  if (field.type === "int" || field.type === "float") {
    const step = field.type === "float" ? "0.1" : "1";
    const min = field.minimum !== undefined ? `min="${field.minimum}"` : "";
    const max = field.maximum !== undefined ? `max="${field.maximum}"` : "";
    return `<input type="number" class="config-input" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val))}" value="${escapeAttr(String(val))}" step="${step}" ${min} ${max} />`;
  }

  // 普通文本（包括 select_provider）
  return `<input type="text" class="config-input" data-path="${escapeAttr(path)}" data-original="${escapeAttr(String(val ?? ""))}" value="${escapeAttr(String(val ?? ""))}" />`;
}

async function saveConfigSection(sectionEl) {
  const updates = collectSectionChanges(sectionEl);
  if (Object.keys(updates).length === 0) {
    showToast("没有修改的配置项", "info");
    return;
  }

  try {
    const result = await bridge.apiPost("dashboard/config/update", { updates });
    showToast(result.message, result.errors && result.errors.length > 0 ? "error" : "success");

    // 更新原始值
    for (const [path, value] of Object.entries(updates)) {
      const input = sectionEl.querySelector(`[data-path="${CSS.escape(path)}"]`);
      if (input) {
        const newValue = input.type === "checkbox" ? input.checked : input.value;
        input.dataset.original = String(newValue);
        configOriginalValues[path] = newValue;
      }
    }

    // 移除已修改标记
    sectionEl.querySelectorAll(".config-field.modified").forEach((el) => {
      el.classList.remove("modified");
    });
  } catch (e) {
    showToast("保存失败: " + e.message, "error");
  }
}

function collectSectionChanges(sectionEl) {
  const updates = {};
  sectionEl.querySelectorAll("[data-path]").forEach((input) => {
    const path = input.dataset.path;
    let currentValue;
    if (input.type === "checkbox") {
      currentValue = input.checked;
    } else if (input.tagName === "SELECT") {
      currentValue = input.value;
    } else if (input.type === "number") {
      currentValue = input.value;
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
  sectionEl.querySelectorAll("[data-path]").forEach((input) => {
    const original = input.dataset.original;
    if (input.type === "checkbox") {
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
    { label: t("browser.installed", "安装状态"), value: data.installed ? "✅ 已安装" : "❌ 未安装" },
    { label: t("browser.type", "浏览器类型"), value: data.browser_type || "—" },
    { label: t("browser.path", "安装路径"), value: data.install_path || "—" },
    { label: t("browser.installTime", "安装时间"), value: data.install_time || "—" },
    { label: t("browser.dirSize", "安装目录大小"), value: data.install_dir_exists ? `${data.install_dir_size_mb} MB` : "—" },
    { label: t("browser.poolSize", "实例池"), value: `${data.browser_pool_size} 个实例` },
    { label: t("browser.installing", "正在安装"), value: data.is_installing ? "是" : "否" },
  ];
  el.innerHTML = rows
    .map(
      (r) => `
    <div class="status-item">
      <span class="status-label">${r.label}</span>
      <span class="status-value">${r.value}</span>
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
    loadPageData(currentPage);
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

  // Browser: uninstall
  document.getElementById("btn-uninstall-browser").addEventListener("click", async () => {
    if (confirm(t("browser.confirmUninstall", "确认卸载浏览器？卸载后截图功能将不可用"))) {
      try {
        const result = await bridge.apiPost("dashboard/browser/uninstall");
        showToast(result.message, "success");
        loadBrowserStatus();
      } catch (e) {
        showToast("卸载失败: " + e.message, "error");
      }
    }
  });

  // Config: toggle checkbox label update (delegated)
  document.getElementById("config-content").addEventListener("change", (e) => {
    if (e.target.classList.contains("config-checkbox")) {
      const label = e.target.closest(".config-toggle")?.querySelector(".config-toggle-label");
      if (label) label.textContent = e.target.checked ? "已启用" : "已禁用";
    }
  });
}

/* ========== Init ========== */
async function init() {
  try {
    await bridge.ready();
    initNavigation();
    initEvents();
    loadPageData("overview");
  } catch (e) {
    console.error("Dashboard init failed:", e);
  }
}

init();
