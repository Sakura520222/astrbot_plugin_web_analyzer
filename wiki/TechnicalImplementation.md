# 技术实现

## 模块结构

```
main.py                     插件入口：命令、助手工具、交付、只读面板 API
core/
  browser.py                CDP 驱动（进程、临时配置、协议多路复用）
  screenshot.py             截图服务：实例池、截图/渲染、诊断、内存监控
  capture_pipeline.py       共用截图流水线：校验 → 缓存 → 截图 → 裁剪
  content_fetcher.py        正文抓取：httpx 流式 / 浏览器渲染
  cache.py                  截图缓存：URL+参数键、内存 LRU + 磁盘
  urls.py                   链接提取、校验、规范化、域名规则
  config_loader.py          配置读取与 v1.x 迁移
  messaging.py              提示消息发送与撤回
  error_handler.py          错误归类与用户可读提示
  constants.py              错误类型与文案
views/
  dashboard/                管理面板（plugin_page）
  screenshot_card/          ChatUI 截图结果卡片（chat_message）
.astrbot-plugin/i18n/       面板与卡片的多语言资源
```

## 截图流水线

自动识别、`/网页截图` 与 `capture_webpage` 工具共用同一条流水线：

1. **提取与校验**：正则提取链接（可选无协议头）；格式校验并拦截内网/回环字面 IP；
2. **访问规则**：黑名单优先，其次允许列表；`www` 归一后去重；
3. **缓存查询**：键 = SHA-256(规范化 URL + 截图参数)；命中直接取图；
4. **截图**：从实例池借出浏览器 → 新建隔离标签页 → 导航 → 按策略等待 → 截图 → 读取 `document.title` 与 `location.href` → 归还实例；
5. **裁剪与缩略图**：按配置裁剪；生成 480px JPEG 缩略图供卡片使用；
6. **写缓存**：JSON 元数据 + 截图二进制同目录存放。

只有实例自身故障（断连、命令超时、进程退出）会更换实例重试；页面加载失败与内容超限不重试。

## 浏览器实例池

- 实例池与检测缓存为类级别状态，启动中 + 使用中 + 空闲实例共享总量上限；
- 达到上限的请求等待归还信号，而非无限启动新进程；取消安全（名额登记在无 await 的临界区内完成）；
- 无法启动的浏览器按真实路径记录（别名去重），10 分钟冷却后重试；
- 每个实例使用独立临时配置（带属主标记，清理只删除属主已退出的目录）。

## 正文抓取

- **HTTP 模式**：httpx 流式读取，手动跟随跳转并在每一跳复用 URL 校验；限制响应体 ≤10 MB、总时长 ≤ 处理超时；
- **浏览器模式**：复用截图服务实例池渲染，校验跳转后的最终地址；
- 两种模式共用可读正文提取：移除 script/style/nav/footer 等干扰元素，按 `article → main → [role=main] → 常见类名 → body` 选择最长文本，按配置截断。

## 缓存

- 键 = SHA-256(URL + width + height + full_page + format + quality + wait_strategy + wait_time)[:32]；
- 有效期只在构造时换算一次（分钟 → 秒），修复旧版重复换算；
- 内存 LRU + 磁盘双层；v1.x 的仅按 URL 键控的旧文件保留在原目录，在列表中标记「旧版」并自然过期。

## 交付

- 原图通过 `Image.fromBytes` 以 base64 直发，不再写临时文件（修复旧版临时文件泄漏）；
- 支持交互视图的平台（`platform_meta.support_ui_interaction` 且宿主提供 `view_result`）额外发送结果卡片，缩略图以 data URL 内嵌在视图快照中（≤1 MiB 限制），历史卡片仅读取快照；不支持的平台发送常规图片消息；
- 自动识别模式下，「继续交给会话模型」开启时经 `context.send_message` 直接发送，事件继续传播给会话模型；关闭时由 handler 返回结果并结束本轮。

## 配置迁移

框架在插件代码运行前会按新 Schema 移除未知配置键。因此新 Schema 把旧版五个中文分组保留为隐藏的 `dict` 类型条目（框架对 `type: dict` 原样保留用户数据），插件首次运行时读取、迁移并删除它们，随后一次性 `save_config()`。

## 测试

- `tests/test_support.py` 桩替 `astrbot.api` 并直载核心模块，测试不触碰宿主数据目录；
- 127 项 Python 测试 + 7 项 Node 前端测试；`WEB_ANALYZER_BROWSER_TESTS=1` 启用本机 Chrome 集成测试（重定向、动态渲染、并发上限、实例故障重试、Cookie 隔离、带认证代理）。
