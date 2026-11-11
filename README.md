<p align="center">
  <img src="logo.png" alt="网页分析插件" width="128">
</p>

# AstrBot 网页分析插件

[![License](https://img.shields.io/github/license/Sakura520222/astrbot_plugin_web_analyzer)](LICENSE)
[![Version](https://img.shields.io/github/v/release/Sakura520222/astrbot_plugin_web_analyzer?include_prereleases)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/releases)

识别消息中的网页链接，提取页面内容并交给 AstrBot 的模型分析。可选截图、翻译、缓存和结果导出。

## 安装

在 AstrBot WebUI 的插件市场搜索“网页分析插件”，或使用[仓库地址](https://github.com/Sakura520222/astrbot_plugin_web_analyzer)安装。手动安装时，将仓库放入 `AstrBot/data/plugins/astrbot_plugin_web_analyzer`，使用 AstrBot 的 Python 环境安装 `requirements.txt` 中的依赖，再重载插件。

截图功能需要在 AstrBot 所在的运行环境中安装 Chrome、Edge 或 Chromium。插件通过 CDP 使用系统浏览器，不会下载浏览器；Docker 部署时需在容器内安装。截图使用独立临时配置，不会读取日常浏览器的 Cookie 或登录状态。

从旧版升级时，`fetch_mode=playwright` 会映射为 `browser`。`/web_browser uninstall` 只清理旧版插件下载的浏览器残留，不会卸载系统浏览器。无需运行 `playwright install`。

## 使用

启用自动模式后，直接发送含网页链接的消息即可分析。也可手动运行：

```text
/网页分析 https://example.com
```

常用命令：

| 命令 | 用途 |
| --- | --- |
| `/网页分析 <URL...>` | 分析一个或多个网页；别名 `/分析`、`/总结`、`/web`、`/analyze` |
| `/web_mode [auto\|manual\|hybrid\|LLMTOOL]` | 查看或切换分析模式 |
| `/web_config` | 查看配置 |
| `/web_cache [clear]` | 查看或清理缓存 |
| `/web_export <URL\|all> [md\|json\|txt]` | 导出分析结果 |
| `/web_browser [uninstall]` | 查看浏览器状态或清理旧版残留 |
| `/web_help` | 查看命令帮助 |

部分管理命令仅限管理员。别名、详细配置和故障排查见[命令说明](wiki/Commands.md)、[配置指南](wiki/Configuration.md)和[常见问题](wiki/FAQ.md)。

## 管理面板

在 WebUI 中打开本插件的 `dashboard` 页面，可管理缓存、域名规则、群聊黑名单、全部配置和浏览器状态。配置按“链接与分析、模型与翻译、输出与截图、消息与会话、网络与资源”排列。

保存后立即应用于后续请求，无需重载插件。正在执行的网络请求可使用原连接完成；浏览器启动参数变更后，旧实例在安全释放后退出。

## 文档与许可

- [快速开始](wiki/QuickStart.md)
- [技术实现](wiki/TechnicalImplementation.md)
- [开发指南](wiki/Development.md)
- [更新记录](CHANGELOG.md)

本项目使用 [MIT License](LICENSE)。
