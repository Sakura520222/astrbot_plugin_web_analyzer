import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const app = await readFile(new URL("../pages/dashboard/app.js", import.meta.url), "utf8");

function field(path, value, type = "text", secret = false) {
  const classes = new Set();
  const clear = { checked: false, disabled: true };
  const hint = { textContent: "" };
  const wrapper = {
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
      contains: (name) => classes.has(name),
    },
    querySelector: (selector) => selector === ".secret-hint" ? hint : null,
  };
  const input = {
    type, tagName: type === "select" ? "SELECT" : "INPUT",
    value: String(value), checked: value === true,
    dataset: { path, original: String(value), ...(secret ? { secret: "true", hasValue: "false" } : {}) },
    closest: () => wrapper,
    checkValidity: () => true,
    reportValidity() {},
  };
  return { input, wrapper, clear, hint, classes };
}

function harness(fields, post = async (_endpoint, { updates }) => ({ applied_paths: Object.keys(updates), errors: [], message: "saved" })) {
  const section = {
    dataset: {},
    querySelectorAll: (selector) => selector.includes(".btn-save-section") ? [] : fields.map(({ input }) => input),
    querySelector(selector) {
      const path = selector.match(/data-(?:path|clear-secret)="([^"]+)"/)?.[1];
      const item = fields.find(({ input }) => input.dataset.path === path);
      return selector.includes("data-clear-secret") ? item?.clear : item?.input;
    },
  };
  const document = {
    querySelector: () => fields.find(({ classes }) => classes.has("modified"))?.wrapper,
    createElement: () => ({ set textContent(value) { this.innerHTML = String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;"); }, innerHTML: "" }),
  };
  const context = vm.createContext({
    window: { AstrBotPluginView: { apiPost: post } },
    document, CSS: { escape: (value) => value }, console, setTimeout,
  });
  vm.runInContext(app.replace(/\binit\(\);\s*$/, ""), context);
  vm.runInContext("showToast = () => {};", context);
  return { section, context, collect: () => context.collectSectionChanges(section), save: () => context.saveConfigSection(section) };
}

test("number fields submit actual JSON numbers, switches remain booleans", () => {
  const number = field("summary", 2000, "number");
  number.input.value = "2500";
  const toggle = field("enabled", false, "checkbox");
  toggle.input.checked = true;
  const { collect } = harness([number, toggle]);
  const updates = collect();
  assert.equal(updates.summary, 2500);
  assert.equal(typeof updates.summary, "number");
  assert.equal(updates.enabled, true);
  assert.match(app, /data-field-path=/);
  assert.doesNotMatch(app, /class="config-field" data-path=/);
});

test("invalid or empty numbers are not saved", async () => {
  const number = field("summary", 2000, "number");
  number.input.value = "";
  let calls = 0;
  const { save } = harness([number], async () => { calls += 1; });
  await save();
  assert.equal(calls, 0);
});

test("save acknowledgements preserve edits made while the request was in flight", async () => {
  const item = field("summary", 2000, "number");
  item.input.value = "2500";
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const { save } = harness([item], () => pending);
  const saving = save();
  item.input.value = "2700";
  resolve({ applied_paths: ["summary"], errors: [], message: "saved" });
  await saving;
  assert.equal(item.input.dataset.original, "2500");
  assert.equal(item.input.value, "2700");
  assert.equal(item.classes.has("modified"), true);
});

test("rejected updates keep the saved baseline and pending edits", async () => {
  const item = field("summary", 2000, "number");
  item.input.value = "2500";
  const { save } = harness([item], async () => { throw new Error("save failed"); });
  await save();
  assert.equal(item.input.dataset.original, "2000");
  assert.equal(item.classes.has("modified"), true);
});

test("secret fields preserve unchanged values and can be replaced then cleared", async () => {
  const secret = field("proxy", "", "password", true);
  const { collect, save } = harness([secret]);
  assert.deepEqual(Object.keys(collect()), []);
  secret.input.value = "http://user:password@localhost:8080";
  await save();
  assert.equal(secret.input.value, "");
  assert.equal(secret.input.dataset.hasValue, "true");
  assert.equal(secret.clear.disabled, false);
  assert.equal(secret.classes.has("modified"), false);
  secret.clear.checked = true;
  assert.equal(collect().proxy, "");
  await save();
  assert.equal(secret.input.dataset.hasValue, "false");
  assert.equal(secret.clear.checked, false);
  assert.equal(secret.clear.disabled, true);
});

test("schema enum labels and all full field paths survive rendering", () => {
  const { context } = harness([]);
  const html = context.buildFieldInput({ path: "分析设置.analysis_mode", value: "auto", type: "string", options: ["auto", "manual"], labels: ["自动分析", "手动命令"] });
  assert.match(html, /value="auto" selected>自动分析<\/option>/);
  assert.match(html, /data-path="分析设置.analysis_mode"/);
});

test("navigation, refresh and browser unload guard pending edits", () => {
  assert.match(app, /window\.addEventListener\("beforeunload"/);
  assert.match(app, /if \(!hasUnsavedConfig\(\)\) return/);
  assert.match(app, /配置有未保存的修改，确定离开此页面吗？/);
  assert.match(app, /配置有未保存的修改，确定重新加载吗？/);
});
