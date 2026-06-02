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
      <td class="url-cell" title="${escapeHtml(item.url)}">${truncateUrl(item.url, 50)}</td>
      <td><span class="badge badge-${item.expired ? "warning" : "success"}">${item.expired ? "已过期" : "有效"}</span></td>
      <td>${item.has_screenshot ? "📷" : "—"}</td>
      <td>${formatTime(item.timestamp)}</td>
      <td><button class="btn btn-sm btn-danger btn-delete-cache" data-url="${escapeHtml(item.url)}">删除</button></td>
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
      <span class="tag-remove" data-type="${type}" data-value="${escapeHtml(item)}">&times;</span>
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
      <span class="tag-remove" data-group-id="${escapeHtml(item)}">&times;</span>
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
async function loadConfig() {
  try {
    const data = await bridge.apiGet("dashboard/config");
    renderConfig(data);
  } catch (e) {
    showToast("加载配置失败: " + e.message, "error");
  }
}

function renderConfig(config) {
  const el = document.getElementById("config-content");
  const sections = [
    { title: t("config.network", "网络设置"), data: config.network },
    { title: t("config.analysis", "分析设置"), data: config.analysis },
    { title: t("config.display", "展示设置"), data: config.display },
    { title: t("config.llm", "智能分析"), data: config.llm },
    { title: t("config.message", "消息管理"), data: config.message },
    { title: t("config.cache", "缓存设置"), data: config.cache },
  ];

  el.innerHTML = sections
    .map(
      (s) => `
    <div class="config-section">
      <h4 class="config-section-title">${s.title}</h4>
      <div class="config-items">
        ${Object.entries(s.data)
          .map(
            ([key, val]) => `
          <div class="config-item">
            <span class="config-key">${key}</span>
            <span class="config-value">${formatConfigValue(val)}</span>
          </div>`
          )
          .join("")}
      </div>
    </div>`
    )
    .join("");
}

function formatConfigValue(val) {
  if (typeof val === "boolean") return val ? "✅" : "❌";
  if (Array.isArray(val)) return val.length > 0 ? val.join(", ") : "—";
  if (val === "" || val === null || val === undefined) return "—";
  return String(val);
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
