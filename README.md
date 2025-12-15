# AstrBot 网页分析插件

[![License](https://img.shields.io/github/license/Sakura520222/astrbot_plugin_web_analyzer)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/blob/main/LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![Version](https://img.shields.io/github/v/release/Sakura520222/astrbot_plugin_web_analyzer?include_prereleases)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/releases)
[![Last Commit](https://img.shields.io/github/last-commit/Sakura520222/astrbot_plugin_web_analyzer)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/commits/main)
[![Dependencies](https://img.shields.io/badge/dependencies-up%20to%20date-brightgreen)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/blob/main/requirements.txt)
[![GitHub Stars](https://img.shields.io/github/stars/Sakura520222/astrbot_plugin_web_analyzer?style=social)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/Sakura520222/astrbot_plugin_web_analyzer?style=social)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/network/members)

这是一个AstrBot插件，能够自动识别用户发送的网页链接，抓取网页内容并调用LLM进行分析和总结，同时支持网页截图功能。

## 更新日志
## [v1.2.8] - 2025-12-15

### ✨ 功能增强
- 增强LLM分析能力，新增多种分析模板，支持智能模板选择
- 完善错误处理机制，实现错误分级和分类
- 优化截图功能，支持截图裁剪
- 改进缓存机制，新增基于内容哈希的缓存策略和缓存预加载
- 优化并发处理，实现基于优先级的任务调度和动态并发控制
- 增强资源管理，新增内存监控和自动释放机制
- 优化结果展示，新增多种结果展示模板和结果折叠功能
- 改进命令系统，支持命令补全和参数提示功能

### 🔄 代码重构
- 重构代码结构，优化依赖关系，统一代码风格
- 重构配置加载流程，确保所有属性在使用前被正确初始化
- 优化组件初始化顺序，避免属性访问错误
- 清理冗余代码，移除未使用的依赖和功能

### 📝 文档更新
- 更新 README.md
- 同步配置文档与代码实现
- 编写详细使用手册，新增配置指南和常见问题解答

> [⚠警告]
> **v1.2.4版本重要更新**：配置文件结构已发生改变，请在AstrBot管理面板中重新设置所有配置项。

详见 [更新日志](CHANGELOG.md) 文件。

## 功能特性

- 🔍 **自动识别URL**: 自动检测消息中的网页链接
- 📄 **智能内容提取**: 使用BeautifulSoup提取网页主要内容
- 🤖 **LLM智能分析**: 集成AstrBot的LLM接口进行深度内容分析
- 📸 **网页截图**: 自动捕获网页截图，直观展示网页外观，支持多种格式和自定义尺寸
- ⚡ **异步并发处理**: 使用asyncio.gather并发处理多个URL，提高性能
- 🎨 **高度可配置**: 支持多种配置选项，满足不同需求
- 🔒 **域名控制**: 支持允许和禁止域名列表
- 📱 **多平台支持**: 兼容各种消息平台
- 📊 **内容统计**: 提供详细的内容统计信息
- 🔗 **多链接处理**: 支持同时处理多条链接，合并成一条合并转发消息发送
- 🌐 **网页翻译**: 支持将网页内容翻译成指定语言
- 📦 **结果缓存**: 支持分析结果缓存，提高重复请求的响应速度
- 🎯 **特定内容提取**: 支持提取图片、链接、代码块、元信息等特定类型内容
- 🧹 **缓存管理**: 支持查看缓存状态和手动清理缓存
- 💾 **分析结果导出**: 支持将分析结果导出为Markdown、JSON、TXT等格式，并作为附件发送
- 🕵️ **代理支持**: 支持HTTP代理配置，可用于绕过访问限制
- 🔄 **请求重试机制**: 自动重试失败的请求，提高抓取成功率
- ✅ **配置验证**: 自动验证配置项的有效性，确保插件稳定运行
- 🎯 **多分析模板**: 新增多种LLM分析模板，支持智能模板选择
- 🚨 **完善的错误处理**: 实现错误分级和分类，提供详细的错误信息
- ✂️ **截图裁剪**: 支持自定义截图区域，裁剪指定部分
- 🔄 **内容哈希缓存**: 基于内容哈希的缓存策略，提高缓存命中率
- ⏳ **缓存预加载**: 支持缓存预加载，提高首次访问速度
- 📈 **优先级调度**: 基于URL优先级的任务调度，提高重要URL的处理速度
- 🔄 **动态并发**: 动态调整并发数，优化资源使用
- 📊 **内存监控**: 新增内存监控和自动释放机制
- 🔄 **浏览器池**: 优化浏览器资源管理，减少资源消耗
- 🎨 **多种结果模板**: 支持多种结果展示模板，满足不同需求
- 📋 **结果折叠**: 支持结果折叠功能，优化长文本展示
- 💬 **命令补全**: 支持命令补全和参数提示功能
- 🔤 **命令别名自定义**: 支持自定义命令别名
- 📚 **详细命令帮助**: 提供完整的命令帮助系统

## Star

[![Star History Chart](https://api.star-history.com/svg?repos=Sakura520222/astrbot_plugin_web_analyzer&type=Date)](https://star-history.com/#Sakura520222/astrbot_plugin_web_analyzer&Date)

## 安装方法

1. 将插件目录复制到AstrBot的插件目录：
   ```bash
   AstrBot/data/plugins/
   ```

2. 安装依赖：
   ```bash
   pip install -r astrbot_plugin_web_analyzer/requirements.txt
   ```

3. 重启AstrBot或重载插件

## 使用方法

### 自动分析

插件会自动检测消息中的URL链接并进行分析：

```
用户：看看这个新闻 https://example.com/news/article
机器人：检测到网页链接，正在分析: https://example.com/news/article
       [分析结果...]
       [网页截图...]
```

支持同时处理多个链接：

```
用户：看看这些新闻 https://example.com/news/article1 https://example.com/news/article2
机器人：检测到2个网页链接，正在分析...
       [合并转发的分析结果...]
       [网页截图...]
```

### 手动分析

使用命令手动分析指定链接：

```
/网页分析 https://example.com
```

支持同时分析多个链接：

```
/网页分析 https://example.com/article1 https://example.com/article2
```

### 命令别名

支持以下命令别名：

```
/分析 https://example.com
/总结 https://example.com
/web https://example.com
/analyze https://example.com
/分析 https://example.com/article1 https://example.com/article2
/总结 https://example.com/article1 https://example.com/article2
/web https://example.com/article1 https://example.com/article2
/analyze https://example.com/article1 https://example.com/article2
```

### 命令帮助

查看所有可用命令和帮助信息：

```
/web_help
```

别名：

```
/网页分析帮助
/网页分析命令
```

### 查看配置

查看当前插件配置：

```
/web_config
```

别名：

```
/网页分析配置
/网页分析设置
```

### 缓存管理

查看缓存状态：

```
/web_cache
```

手动清理缓存：

```
/web_cache clear
```

别名：

```
/网页缓存
/清理缓存
```

### 分析结果导出

导出指定URL的分析结果：

```
/web_export https://example.com md
```

导出所有缓存的分析结果：

```
/web_export all json
```

支持的格式：

- `md` 或 `markdown`: Markdown格式，适合阅读和分享
- `json`: JSON格式，适合程序处理和数据交换
- `txt`: 纯文本格式，兼容性好

别名：

```
/导出分析结果 https://example.com
/网页导出 all md
```

### 群聊黑名单管理

查看当前群聊黑名单：

```
/group_blacklist
```

添加群聊到黑名单：

```
/group_blacklist add <群号>
```

从黑名单移除群聊：

```
/group_blacklist remove <群号>
```

清空黑名单：

```
/group_blacklist clear
```

别名：

```
/群黑名单
/黑名单
```

## 配置选项

插件支持多种配置选项，可以在AstrBot管理面板中进行设置：

### 基本设置

- **max_content_length**: 最大网页内容长度（默认：10000）
- **request_timeout**: 请求超时时间(秒)（默认：30）
- **retry_count**: 请求重试次数（默认：3）
- **retry_delay**: 请求重试间隔(秒)（默认：2）
- **llm_enabled**: 启用LLM智能分析（默认：true）
- **auto_analyze**: 自动分析检测到的链接（默认：true）
- **user_agent**: 自定义User-Agent
- **proxy**: HTTP代理配置，格式为http://username:password@host:port ，留空表示不使用代理

### 域名控制

- **allowed_domains**: 允许的域名列表（留空表示允许所有域名）
- **blocked_domains**: 禁止的域名列表

### 分析设置

- **enable_emoji**: 启用emoji图标（默认：true）
- **enable_statistics**: 显示内容统计（默认：true）
- **max_summary_length**: 最大摘要长度（默认：2000）
- **enable_screenshot**: 启用网页截图（默认：true）
- **screenshot_quality**: 截图质量（0-100，默认：80）
- **screenshot_width**: 截图宽度像素（默认：1280）
- **screenshot_height**: 截图高度像素（默认：720）
- **screenshot_format**: 截图格式（支持jpeg和png，默认：jpeg）
- **screenshot_full_page**: 截取整页（默认：false）
- **screenshot_wait_time**: 截图前等待页面加载的时间（毫秒，默认：2000）
- **result_template**: 结果展示模板，支持：default, detailed, compact, markdown, simple（默认：default）
- **enable_collapsible**: 启用结果折叠功能（默认：false）
- **collapse_threshold**: 结果折叠阈值（默认：1500）

### 截图高级设置

- **enable_crop**: 启用截图裁剪功能（默认：false）
- **crop_area**: 裁剪区域，格式为 [left, top, right, bottom]（默认：[0, 0, screenshot_width, screenshot_height]）

### LLM配置

- **llm_provider**: LLM提供商（使用会话默认或指定提供商）
- **custom_prompt**: 自定义分析提示词

### 群聊控制

- **group_blacklist**: 群聊黑名单，在这些群聊中禁用自动分析功能

### 合并转发

- **merge_forward_enabled.group**: 群聊启用合并转发功能（默认：false）
- **merge_forward_enabled.private**: 私聊启用合并转发功能（默认：false）

### 翻译设置

- **enable_translation**: 启用网页翻译（默认：false）
- **target_language**: 目标语言（默认：zh）
- **translation_provider**: 翻译提供商（默认：llm）
- **custom_translation_prompt**: 自定义翻译提示词

### 缓存设置

- **enable_cache**: 启用结果缓存（默认：true）
- **cache_expire_time**: 缓存过期时间（分钟，默认：1440）
- **max_cache_size**: 最大缓存数量（默认：100）
- **cache_preload_enabled**: 启用缓存预加载功能（默认：false）
- **cache_preload_count**: 预加载的缓存数量（默认：20）

### 内容提取设置

- **enable_specific_extraction**: 启用特定内容提取（默认：false）
- **extract_types**: 提取内容类型，每行一个，支持：title, content, images, links, tables, lists, code, meta（默认：title\ncontent）

## 技术实现

### 网页内容提取

- 使用 `httpx` 进行异步HTTP请求
- 使用 `BeautifulSoup` 和 `lxml` 解析HTML
- 智能选择主要内容区域（article、main等语义化标签）
- 移除脚本和样式标签，只保留纯文本内容
- 支持代理配置，可用于绕过访问限制
- 实现了请求重试机制，提高抓取成功率

### 异步并发处理

- 使用 `asyncio.gather` 并发处理多个URL
- 优化了异步上下文管理器的使用
- 提高了多链接处理的效率

### 网页截图

- 使用 `playwright` 进行无头浏览器截图
- 支持自定义截图质量、宽度、高度和等待时间
- 支持多种截图格式（JPEG和PNG）
- 自动安装浏览器，无需手动配置

### 缓存系统

- 实现了内存缓存和文件缓存双重机制
- 支持缓存统计、过期清理和大小限制
- 提供了缓存管理命令

### LLM分析

- 集成AstrBot的LLM接口
- 提供结构化的分析提示词
- 支持多种分析维度：
  - 核心摘要
  - 关键要点
  - 内容类型
  - 价值评估
  - 适用人群

### 配置系统

- 添加了配置验证逻辑，确保配置项的有效性
- 提供了详细的配置错误提示
- 支持多种配置选项，满足不同需求

### 错误处理

- 网络请求失败时的友好提示
- LLM不可用时的基础分析模式
- 完善的日志记录
- 浏览器自动安装和错误恢复
- 资源的正确释放和清理

## 依赖说明

- `httpx>=0.24.0`: 异步HTTP客户端
- `beautifulsoup4>=4.12.0`: HTML解析库
- `lxml>=4.9.0`: 快速XML/HTML解析器
- `playwright>=1.40.0`: 浏览器自动化库，用于网页截图

## 常见问题

### 截图功能不工作

如果截图功能不工作，可能是因为：

1. 浏览器未正确安装 - 插件会自动尝试安装浏览器
2. 网络问题 - 请检查网络连接
3. 权限问题 - 确保插件有足够的权限创建临时文件
4. 截图格式设置错误 - 请确保使用支持的格式（JPEG或PNG）

### 分析结果不准确

如果分析结果不准确，可以尝试：

1. 调整 `max_content_length` 配置，增加抓取的内容长度
2. 调整 `screenshot_wait_time` 配置，增加页面加载等待时间
3. 使用自定义提示词，优化分析结果
4. 检查代理配置是否正确 - 如果使用了代理

### 插件响应缓慢

如果插件响应缓慢，可以尝试：

1. 减少 `max_content_length` 配置，减少抓取的内容长度
2. 关闭 `screenshot_full_page` 选项，只截取可见部分
3. 调整 `request_timeout` 配置，减少超时时间
4. 减少 `retry_count` 配置，减少重试次数
5. 关闭 `enable_screenshot` 选项，禁用截图功能

### 代理配置不工作

如果代理配置不工作，可以尝试：

1. 检查代理格式是否正确 - 格式应为 http://username:password@host:port
2. 检查代理服务器是否可用
3. 确保代理服务器支持HTTPS请求

### 缓存不生效

如果缓存不生效，可以尝试：

1. 检查 `enable_cache` 配置是否为 true
2. 检查 `cache_expire_time` 配置是否合理
3. 尝试手动清理缓存后重新测试
4. 检查缓存目录是否有写入权限

## 开发说明

插件遵循AstrBot插件开发规范：

- 使用中文注释
- 完善的错误处理
- 异步编程模式
- 符合PEP8代码风格

## 许可证

本项目采用 [MIT License](LICENSE) 开源协议。