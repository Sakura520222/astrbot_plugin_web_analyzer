const PLUGIN_NAME = "astrbot_plugin_web_analyzer";

const bridge = window.AstrBotPluginView || window.AstrBotPluginPage;

/* ========== i18n ========== */
function t(key, fallback) {
  const missing = "__web_analyzer_missing__";
  const preferred = bridge.t(`views.dashboard.${key}`, missing);
  return preferred === missing ? bridge.t(`pages.dashboard.${key}`, fallback) : fallback;
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
let cacheSearchTimer = null;
const PREVIEW_CACHE = new Map();

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
    item.addEventListener("click", () => switchPage(item.dataset.page));
  });
}

const PAGE_TITLES = {
  overview: "截图概览",
  cache: "截图缓存",
  rules: "访问规则",
  diagnostics: "浏览器诊断",
};

function switchPage(page) {
  if (page === currentPage) return;
  currentPage = page;
  document.querySelectorAll(".nav-item").forEach((el) => {
    const active = el.dataset.page === page;
    el.classList.toggle("active", active);
    if (active) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("active"));
  document.getElementById(`page-${page}`).classList.add("active");
  const label = document.querySelector(`.nav-item[data-page="${page}"] .nav-text`);
  document.getElementById("page-title").textContent = label?.textContent || t(`nav.${page}`, PAGE_TITLES[page] || page);
  loadPageData(page);
}

/* ========== Data Loading ========== */
async function loadPageData(page) {
  switch (page) {
    case "overview":
      await Promise.all([loadOverview(), loadBrowserSummary()]);
      break;
    case "cache":
      await loadCache();
      break;
    case "rules":
      await loadRules();
      break;
    case "diagnostics":
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

    renderAutoStatus(data);
    renderCaptureParams(data.screenshot);
  } catch (e) {
    showToast(t("error.loadFailed", "加载概览数据失败: ") + e.message, "error");
  }
}

async function loadBrowserSummary() {
  try {
    const status = await bridge.apiGet("dashboard/browser");
    const el = document.getElementById("stat-browser");
    if (status.installed) {
      el.textContent = status.browser_type || "已检测";
      el.classList.remove("state-disabled");
      el.classList.add("state-enabled");
    } else {
      el.textContent = t("overview.browserMissing", "未检测到");
      el.classList.remove("state-enabled");
      el.classList.add("state-disabled");
    }
  } catch (e) {
    document.getElementById("stat-browser").textContent = "—";
  }
}

function renderAutoStatus(data) {
  const el = document.getElementById("auto-status");
  const items = [
    {
      label: t("overview.autoCapture", "自动识别链接"),
      value: data.auto_capture ? "已启用" : "已禁用",
      state: data.auto_capture,
    },
    {
      label: t("overview.handoff", "继续交给会话模型"),
      value: data.handoff_to_model ? "已启用" : "已禁用",
      state: data.handoff_to_model,
    },
    {
      label: t("overview.concurrency", "批量并发上限"),
      value: data.max_concurrency,
      color: "blue",
    },
  ];
  el.innerHTML = items
    .map(
      (i) => `
    <div class="status-item">
      <span class="status-label">${escapeHtml(i.label)}</span>
      <span class="status-value ${i.color === "blue" ? "text-blue" : i.state ? "state-enabled" : "state-disabled"}">${escapeHtml(String(i.value ?? ""))}</span>
    </div>`
    )
    .join("");
}

function renderCaptureParams(params) {
  const el = document.getElementById("capture-params");
  const waitLabels = { fixed: "固定等待", networkidle: "网络空闲", smart: "空闲后短暂等待" };
  const items = [
    { label: t("capture.viewport", "视口尺寸"), value: `${params.width} × ${params.height}` },
    { label: t("capture.fullPage", "截取整页"), value: params.full_page ? "是" : "否" },
    { label: t("capture.format", "格式"), value: `${params.format.toUpperCase()}${params.format === "jpeg" ? ` · 质量 ${params.quality}` : ""}` },
    { label: t("capture.wait", "加载等待"), value: `${waitLabels[params.wait_strategy] || params.wait_strategy} · ${params.wait_ms}ms` },
    { label: t("capture.crop", "裁剪"), value: params.crop_enabled ? "已启用" : "未启用", state: params.crop_enabled },
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

/* ========== Cache ========== */
async function loadCache() {
  try {
    const query = document.getElementById("cache-search").value.trim();
    const data = await bridge.apiGet("dashboard/cache", query ? { query } : undefined);
    document.getElementById("cache-total").textContent = data.stats.total;
    document.getElementById("cache-valid").textContent = data.stats.valid;
    document.getElementById("cache-expired").textContent = data.stats.expired;
    renderCacheTable(data.items);
  } catch (e) {
    showToast(t("error.loadFailed", "加载缓存数据失败: ") + e.message, "error");
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
      <td class="url-cell" title="${escapeAttr(item.url)}"><a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer noopener">${truncateUrl(item.url, 46)}</a></td>
      <td class="title-cell" title="${escapeAttr(item.title || "")}">${escapeHtml(truncate(item.title || "—", 24))}${item.legacy ? ` <span class="badge badge-warning">${t("cache.legacy", "旧版")}</span>` : ""}</td>
      <td><span class="badge badge-${item.expired ? "warning" : "success"}">${item.expired ? t("cache.expiredLabel", "已过期") : t("cache.validLabel", "有效")}</span></td>
      <td>${formatTime(item.timestamp)}</td>
      <td>
        ${item.has_screenshot ? `<button class="btn btn-sm btn-secondary btn-preview" data-id="${escapeAttr(item.id)}" ${item.expired ? "data-expired=\"1\"" : ""}>${t("cache.preview", "预览")}</button>` : ""}
        <button class="btn btn-sm btn-danger btn-delete-cache" data-id="${escapeAttr(item.id)}">${t("cache.delete", "删除")}</button>
      </td>
    </tr>`
    )
    .join("");

  tbody.querySelectorAll(".btn-preview").forEach((btn) => {
    btn.addEventListener("click", () => openPreview(btn.dataset.id, btn.dataset.expired === "1"));
  });
  tbody.querySelectorAll(".btn-delete-cache").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!(await confirmDialog(t("cache.confirmDelete", "确认删除此缓存？")))) return;
      try {
        await bridge.apiPost("dashboard/cache/delete", { id: btn.dataset.id });
        showToast(t("cache.deleted", "缓存已删除"), "success");
        loadCache();
      } catch (e) {
        showToast(t("error.actionFailed", "操作失败: ") + e.message, "error");
      }
    });
  });
}

async function openPreview(id, expired) {
  const overlay = document.getElementById("preview-overlay");
  const img = document.getElementById("preview-image");
  try {
    let dataUrl = PREVIEW_CACHE.get(id);
    if (!dataUrl) {
      const result = await bridge.apiGet("dashboard/cache/preview", { id, allow_expired: expired ? "1" : "" });
      dataUrl = result.data_url;
      PREVIEW_CACHE.set(id, dataUrl);
    }
    img.src = dataUrl;
    overlay.hidden = false;
  } catch (e) {
    showToast(t("cache.previewFailed", "预览加载失败: ") + e.message, "error");
  }
}

function closePreview() {
  document.getElementById("preview-overlay").hidden = true;
  document.getElementById("preview-image").src = "";
}

/* ========== Confirm dialog ========== */
// 宿主 iframe 的 sandbox 不含 allow-modals，window.confirm 被静默忽略，
// 必须使用页面内的确认对话框。
function confirmDialog(message) {
  return new Promise((resolve) => {
    const overlay = document.getElementById("confirm-overlay");
    const messageEl = document.getElementById("confirm-message");
    const okBtn = document.getElementById("btn-confirm-ok");
    const cancelBtn = document.getElementById("btn-confirm-cancel");
    const previousFocus = document.activeElement;
    messageEl.textContent = message;
    overlay.hidden = false;

    const done = (result) => {
      overlay.hidden = true;
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      window.removeEventListener("keydown", onKey);
      if (previousFocus && typeof previousFocus.focus === "function") {
        previousFocus.focus();
      }
      resolve(result);
    };
    const onOk = () => done(true);
    const onCancel = () => done(false);
    const onKey = (event) => {
      if (event.key === "Escape") done(false);
    };

    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    window.addEventListener("keydown", onKey);
    cancelBtn.focus();
  });
}

/* ========== Rules (read-only) ========== */
async function loadRules() {
  try {
    const data = await bridge.apiGet("dashboard/rules");
    renderTagList("allowed-domains-list", data.allowed_domains, "success");
    renderTagList("blocked-domains-list", data.blocked_domains, "danger");
    renderTagList("group-blacklist-list", data.group_blacklist, "danger");
  } catch (e) {
    showToast(t("error.loadFailed", "加载访问规则失败: ") + e.message, "error");
  }
}

function renderTagList(elementId, values, tone) {
  const el = document.getElementById(elementId);
  if (!values || values.length === 0) {
    el.innerHTML = `<span class="empty-tag">${t("rules.empty", "暂无条目")}</span>`;
    return;
  }
  el.innerHTML = values
    .map((value) => `<span class="tag tag-${tone}">${escapeHtml(value)}</span>`)
    .join("");
}

/* ========== Browser diagnostics ========== */
async function loadBrowserStatus() {
  const el = document.getElementById("browser-status");
  const legacyEl = document.getElementById("legacy-status");
  try {
    const status = await bridge.apiGet("dashboard/browser");
    renderBrowserStatus(el, status);
    renderLegacyStatus(legacyEl, status);
  } catch (e) {
    el.innerHTML = `<div class="empty-state">${t("error.loadFailed", "加载失败: ") + escapeHtml(e.message)}</div>`;
  }
}

function renderBrowserStatus(el, status) {
  const rows = [];
  if (status.installed) {
    rows.push({ label: t("diagnostics.browserType", "浏览器"), value: status.browser_type || "—" });
    rows.push({ label: t("diagnostics.browserVersion", "版本"), value: status.browser_version || "—" });
    rows.push({ label: t("diagnostics.browserPath", "路径"), value: status.install_path || "—" });
    rows.push({
      label: t("diagnostics.pool", "实例池"),
      value: `${t("diagnostics.idle", "空闲")} ${status.browser_pool_size} · ${t("diagnostics.active", "在用+启动中")} ${status.browser_instances} · ${t("diagnostics.limit", "上限")} ${status.max_browser_instances}`,
    });
  } else {
    rows.push({
      label: t("diagnostics.detected", "检测结果"),
      value: t("diagnostics.notFound", "未检测到系统浏览器，请安装 Chrome / Edge / Chromium"),
      state: false,
    });
  }
  if (status.skipped_browsers && Object.keys(status.skipped_browsers).length > 0) {
    const detail = Object.entries(status.skipped_browsers)
      .map(([path, info]) => `${path}: ${info.reason} (~${info.expires_in_min} min)`)
      .join("\n");
    rows.push({ label: t("diagnostics.skipped", "暂时跳过"), value: detail });
  }
  el.innerHTML = rows
    .map(
      (r) => `
    <div class="status-item">
      <span class="status-label">${escapeHtml(r.label)}</span>
      <span class="status-value ${r.state === false ? "state-disabled" : ""}" style="${r.value && String(r.value).includes("\n") ? "white-space: pre-line;" : ""}">${escapeHtml(String(r.value ?? ""))}</span>
    </div>`
    )
    .join("");
}

function renderLegacyStatus(el, status) {
  if (status.legacy_dir_exists) {
    el.innerHTML = `<div class="status-item"><span class="status-label">${t("diagnostics.legacyFound", "发现旧版残留")}</span><span class="status-value state-disabled">${status.legacy_dir_size_mb} MB</span></div>`;
  } else {
    el.innerHTML = `<div class="status-item"><span class="status-label">${t("diagnostics.legacyFound", "发现旧版残留")}</span><span class="status-value state-enabled">${t("diagnostics.legacyNone", "无")}</span></div>`;
  }
}

/* ========== Events ========== */
function initEvents() {
  document.getElementById("btn-refresh").addEventListener("click", () => loadPageData(currentPage));

  document.getElementById("card-clear-cache").addEventListener("click", async () => {
    if (!(await confirmDialog(t("cache.confirmClear", "确认清空所有缓存？此操作不可恢复")))) return;
    try {
      const result = await bridge.apiPost("dashboard/cache/clear");
      showToast(result.message || t("cache.cleared", "已清空"), "success");
      PREVIEW_CACHE.clear();
      loadCache();
    } catch (e) {
      showToast(t("error.actionFailed", "操作失败: ") + e.message, "error");
    }
  });

  const search = document.getElementById("cache-search");
  search.addEventListener("input", () => {
    clearTimeout(cacheSearchTimer);
    cacheSearchTimer = setTimeout(loadCache, 300);
  });

  document.getElementById("btn-preview-close").addEventListener("click", closePreview);
  document.getElementById("preview-overlay").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closePreview();
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.getElementById("preview-overlay").hidden) closePreview();
  });

  document.getElementById("btn-refresh-browser").addEventListener("click", loadBrowserStatus);
  document.getElementById("btn-recheck").addEventListener("click", async () => {
    document.getElementById("browser-status").innerHTML = '<div class="loading-spinner" role="status"></div>';
    try {
      await bridge.apiPost("dashboard/browser/recheck");
      loadBrowserStatus();
    } catch (e) {
      showToast(t("error.actionFailed", "操作失败: ") + e.message, "error");
    }
  });
  document.getElementById("btn-uninstall-browser").addEventListener("click", async () => {
    if (!(await confirmDialog(t("diagnostics.confirmCleanup", "确认清理旧版浏览器残留文件？")))) return;
    try {
      const result = await bridge.apiPost("dashboard/browser/cleanup");
      showToast(result.message || "done", result.success ? "success" : "error");
      loadBrowserStatus();
    } catch (e) {
      showToast(t("error.actionFailed", "操作失败: ") + e.message, "error");
    }
  });
}

/* ========== Utils ========== */
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function truncate(value, max) {
  return value.length > max ? value.slice(0, max - 1) + "…" : value;
}

function truncateUrl(url, max) {
  return truncate(url, max);
}

function formatTime(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
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
