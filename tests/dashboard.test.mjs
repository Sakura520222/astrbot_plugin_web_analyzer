import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const app = await readFile(
  new URL("../views/dashboard/app.js", import.meta.url),
  "utf8",
);

function makeElement(extra = {}) {
  const listeners = {};
  const element = {
    textContent: "",
    innerHTML: "",
    value: "",
    hidden: true,
    dataset: {},
    listeners,
    focus() {},
    classList: {
      add() {},
      remove() {},
      toggle(name, enabled) {},
    },
    setAttribute() {},
    removeAttribute() {},
    addEventListener(name, handler) {
      listeners[name] = handler;
    },
    removeEventListener(name, handler) {
      if (listeners[name] === handler) delete listeners[name];
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    appendChild() {},
    ...extra,
  };
  return { element, listeners };
}

function buildHarness({ overviewData, cacheData, browserData, rulesData }) {
  const apiCalls = [];
  const elements = new Map();
  const byId = (id, extra) => {
    if (!elements.has(id)) elements.set(id, makeElement(extra));
    return elements.get(id).element;
  };

  const bridge = {
    t: (key, fallback) => fallback,
    async ready() {},
    getContext: () => ({ isDark: false, locale: "zh-CN" }),
    onContext: () => () => {},
    async apiGet(endpoint, params) {
      apiCalls.push({ endpoint, params });
      if (endpoint.endsWith("overview")) return overviewData;
      if (endpoint.endsWith("cache")) return cacheData;
      if (endpoint.endsWith("browser")) return browserData;
      if (endpoint.endsWith("rules")) return rulesData;
      return {};
    },
    async apiPost(endpoint, body) {
      apiCalls.push({ endpoint, body });
      return { message: "ok", success: true };
    },
  };

  const toastContainer = makeElement();
  const context = {
    window: {
      addEventListener() {},
      confirm: () => true,
    },
    document: {
      documentElement: { dataset: {}, lang: "" },
      getElementById: (id) =>
        id === "toast-container" ? toastContainer.element : byId(id),
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => makeElement().element,
    },
    console,
    setTimeout: (fn) => 0,
    clearTimeout: () => {},
    confirm: () => true,
    window_AstrBotPluginView: bridge,
    AstrBotPluginView: bridge,
    AstrBotPluginPage: undefined,
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(
    "const window = AstrBotPluginView ? { AstrBotPluginView, addEventListener() {}, removeEventListener() {}, confirm() { return true; } } : null;\n" +
      app,
    context,
  );
  return { context, apiCalls, byId, elements };
}

const OVERVIEW = {
  cache_stats: { total: 3, valid: 2, expired: 1 },
  auto_capture: true,
  handoff_to_model: false,
  max_concurrency: 4,
  screenshot: {
    width: 1280,
    height: 720,
    full_page: false,
    format: "jpeg",
    quality: 80,
    wait_strategy: "fixed",
    wait_ms: 2000,
    crop_enabled: false,
  },
};
const BROWSER = {
  installed: true,
  install_path: "C:/chrome.exe",
  browser_type: "Google Chrome",
  browser_version: "130",
  browser_pool_size: 1,
  browser_instances: 0,
  max_browser_instances: 3,
  skipped_browsers: {},
  legacy_dir_exists: false,
  legacy_dir_size_mb: 0,
};
const CACHE = {
  stats: { total: 1, valid: 1, expired: 0 },
  items: [
    {
      id: "abc123",
      url: "https://example.com/<script>",
      title: 'Tit"le',
      timestamp: 1730000000,
      expired: false,
      has_screenshot: true,
      legacy: false,
    },
  ],
};
const RULES = {
  allowed_domains: ["a.com"],
  blocked_domains: [],
  enable_unified_domain: false,
  group_blacklist: ["1"],
  auto_capture: true,
};

test("init loads overview and browser summary", async () => {
  const { apiCalls, byId } = buildHarness({
    overviewData: OVERVIEW,
    browserData: BROWSER,
    cacheData: CACHE,
    rulesData: RULES,
  });
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.ok(apiCalls.some((c) => c.endpoint.endsWith("overview")));
  assert.ok(apiCalls.some((c) => c.endpoint.endsWith("browser")));
  assert.equal(byId("stat-cache-total").textContent, 3);
  assert.equal(byId("stat-cache-valid").textContent, 2);
  assert.equal(byId("stat-cache-expired").textContent, 1);
});

test("cache table escapes html in url and title", async () => {
  const { context, byId } = buildHarness({
    overviewData: OVERVIEW,
    browserData: BROWSER,
    cacheData: CACHE,
    rulesData: RULES,
  });
  await new Promise((resolve) => setTimeout(resolve, 10));
  await context.loadPageData("cache");
  const html = byId("cache-table-body").innerHTML;
  assert.ok(html.includes("&lt;script&gt;"), "script tag must be escaped");
  assert.ok(html.includes("&quot;"), "quotes must be escaped");
  assert.ok(html.includes("btn-preview"), "preview button rendered");
  assert.ok(html.includes("btn-delete-cache"), "delete button rendered");
});

test("formatTime renders a sortable timestamp", async () => {
  const { context } = buildHarness({
    overviewData: OVERVIEW,
    browserData: BROWSER,
    cacheData: CACHE,
    rulesData: RULES,
  });
  const formatted = context.formatTime(1730000000);
  assert.match(formatted, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  assert.equal(context.formatTime(0), "—");
});

test("escapeHtml neutralizes markup", async () => {
  const { context } = buildHarness({
    overviewData: OVERVIEW,
    browserData: BROWSER,
    cacheData: CACHE,
    rulesData: RULES,
  });
  assert.equal(
    context.escapeHtml('<img src=x onerror="a(\'b\')">'),
    "&lt;img src=x onerror=&quot;a(&#39;b&#39;)&quot;&gt;",
  );
});

test("truncate caps long strings with an ellipsis", async () => {
  const { context } = buildHarness({
    overviewData: OVERVIEW,
    browserData: BROWSER,
    cacheData: CACHE,
    rulesData: RULES,
  });
  assert.equal(context.truncate("abcdef", 4), "abc…");
  assert.equal(context.truncate("ab", 4), "ab");
});

test("browser status renders skipped entries with a pre-line value", async () => {
  const { context, byId } = buildHarness({
    overviewData: OVERVIEW,
    browserData: {
      ...BROWSER,
      skipped_browsers: {
        "/usr/bin/chrome": { reason: "cannot execute", expires_in_min: 9 },
      },
    },
    cacheData: CACHE,
    rulesData: RULES,
  });
  await new Promise((resolve) => setTimeout(resolve, 10));
  await context.loadPageData("diagnostics");
  const html = byId("browser-status").innerHTML;
  assert.ok(html.includes("chrome"));
  assert.ok(html.includes("cannot execute"));
});

test("rules page renders tag lists", async () => {
  const { context, byId } = buildHarness({
    overviewData: OVERVIEW,
    browserData: BROWSER,
    cacheData: CACHE,
    rulesData: RULES,
  });
  await new Promise((resolve) => setTimeout(resolve, 10));
  await context.loadPageData("rules");
  assert.ok(byId("allowed-domains-list").innerHTML.includes("a.com"));
  assert.ok(byId("group-blacklist-list").innerHTML.includes("1"));
});

test("confirmDialog resolves via buttons and hides the overlay", async () => {
  const { context, byId } = buildHarness({
    overviewData: OVERVIEW,
    browserData: BROWSER,
    cacheData: CACHE,
    rulesData: RULES,
  });
  await new Promise((resolve) => setTimeout(resolve, 10));

  const pending = context.confirmDialog("确认清空？");
  const overlay = byId("confirm-overlay");
  assert.equal(overlay.hidden, false, "overlay should be visible");
  assert.equal(byId("confirm-message").textContent, "确认清空？");

  byId("btn-confirm-cancel").listeners.click();
  const cancelled = await pending;
  assert.equal(cancelled, false);
  assert.equal(overlay.hidden, true, "overlay should hide after cancel");

  const pendingOk = context.confirmDialog("再次确认");
  byId("btn-confirm-ok").listeners.click();
  assert.equal(await pendingOk, true);
  assert.equal(overlay.hidden, true);
});
