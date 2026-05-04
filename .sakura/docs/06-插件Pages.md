# 插件 Pages

> 来源: https://docs.astrbot.app/dev/star/guides/plugin-pages.html

---

AstrBot 支持插件通过 `pages/` 目录暴露 Dashboard 页面。`pages/` 下的每个一级子目录都是一个独立 Page：

```
astrbot_plugin_page_demo/
├─ main.py
└─ pages/
   ├─ bridge-demo/
   │  ├─ index.html
   │  ├─ app.js
   │  ├─ style.css
   │  └─ assets/
   │     └─ logo.svg
   └─ settings/
      └─ index.html
```

AstrBot 会扫描 `pages/<page_name>/index.html`；没有 `index.html` 的目录会被忽略。

> **NOTE**: 如果只是让用户填写几个配置项，优先使用 `_conf_schema.json`。插件 Pages 更适合复杂表单、Dashboard、日志、文件上传下载、SSE 和自定义交互流程。

一旦注册了 Pages，用户可以在：AstrBot WebUI 插件页中的插件卡片中，点击插件卡片进入插件详细页面，在插件详细页面中可以看到并进入注册的 Pages。

## 最小前端示例

`pages/bridge-demo/index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>Plugin Page Demo</title>
    <link rel="stylesheet" href="./style.css" />
  </head>
  <body>
    <button id="ping">Ping</button>
    <pre id="output"></pre>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

`pages/bridge-demo/app.js`：

```javascript
const bridge = window.AstrBotPluginPage;
const output = document.getElementById("output");

const context = await bridge.ready();
output.textContent = JSON.stringify(context, null, 2);

document.getElementById("ping").addEventListener("click", async () => {
  const res = await bridge.apiPost("ping");
  output.textContent = JSON.stringify(res, null, 2);
});
```

## 后端注册路由

在插件的 `main.py` 中注册 Page 路由：

```python
from flask import jsonify, request

class Main(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 注册页面路由
        self.register_page("bridge-demo")
        self.register_api_route("bridge-demo", "/ping", ["GET", "POST"], self.page_ping)

    async def page_ping(self):
        return jsonify({"message": "pong"})
```

## Bridge API

插件 Page 中可直接使用 `window.AstrBotPluginPage`：

| 方法 | 说明 |
|------|------|
| `ready()` | 获取插件上下文信息，返回 Promise |
| `getContext()` | 获取当前上下文 |
| `apiGet(endpoint, params)` | GET 请求 |
| `apiPost(endpoint, body)` | POST 请求 |
| `upload(endpoint, file)` | 上传文件（`multipart/form-data`） |
| `download(endpoint, params, filename)` | 下载文件 |
| `subscribeSSE(endpoint, handlers, params)` | 订阅 SSE 事件流 |
| `unsubscribeSSE(subscriptionId)` | 取消订阅 SSE |

当前 `ready()` 上下文类似：

```json
{
  "pluginName": "astrbot_plugin_page_demo",
  "displayName": "Plugin Page Demo"
}
```

> **NOTE**: `endpoint` 必须是插件内相对路径，不能为空，不能包含 `\`、URL scheme、query、hash，也不能包含 `.` 或 `..` 路径片段。

## 静态资源路径规则

AstrBot 会重写相对资源路径，并自动补上短期 `asset_token`。你只需要正常写相对路径，不要自己拼接 `/api/plugin/page/content/...`。
