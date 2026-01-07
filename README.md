# AstrBot 网页分析插件

[![License](https://img.shields.io/github/license/Sakura520222/astrbot_plugin_web_analyzer)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/blob/main/LICENSE)
[![Version](https://img.shields.io/github/v/release/Sakura520222/astrbot_plugin_web_analyzer?include_prereleases)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/releases)
[![Last Commit](https://img.shields.io/github/last-commit/Sakura520222/astrbot_plugin_web_analyzer)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/commits/main)
[![GitHub Stars](https://img.shields.io/github/stars/Sakura520222/astrbot_plugin_web_analyzer?style=social)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/Sakura520222/astrbot_plugin_web_analyzer?style=social)](https://github.com/Sakura520222/astrbot_plugin_web_analyzer/network/members)

AstrBot网页分析插件，能够自动识别用户发送的网页链接，智能抓取解析内容，集成大语言模型进行深度分析和总结，支持网页截图、缓存机制和多种管理命令。

## 更新日志

## [v1.4.0] - 2026-01-07

### ✨ 功能增强
- 增强内容提取功能：支持提取视频、音频、引用、标题、段落、按钮和表单等多种内容类型
- 扩展`extract_specific_content`方法，实现对各类内容的详细提取逻辑
- 优化图片提取，包含alt文本信息
- 新增自定义模板支持：允许用户通过配置自定义分析结果的输出格式
- 实现`_load_template_settings`方法加载模板配置
- 新增`_render_custom_template`方法，支持变量替换的模板渲染
- 增强`_apply_result_settings`方法，支持应用自定义模板

### ⚙️ 配置调整
- 在`_conf_schema.json`中添加`template_settings`配置项
- 支持启用/禁用自定义模板
- 支持配置模板内容和格式
- 更新`validate_extract_types`方法，支持验证新增的内容类型

## [v1.3.9] - 2026-01-07

### 🐛 Bug修复
- 修复Telegram平台事件处理错误：解决'TelegramPlatformEvent' object has no attribute 'bot'问题，使插件能够兼容不同类型的事件对象
- 优化_send_processing_message方法，添加bot属性检查，确保在没有bot实例时仍能正常发送消息
- 修复特定内容提取不工作的问题：将analysis_result += specific_content_str代码的缩进调整到元信息处理条件判断的外部，确保无论网页是否包含元信息，都会将提取到的特定内容添加到分析结果中
- 修复依赖缺失问题：在requirements.txt中添加pyee>=11.0.0依赖，解决部分环境网页截图功能中可能出现的"No module named 'pyee.asyncio'"错误

> [⚠警告]
> **v1.2.4版本重要更新**：配置文件结构已发生改变，请在AstrBot管理面板中重新设置所有配置项。

详见 [更新日志](CHANGELOG.md) 文件。

## 功能特性

- **自动识别URL**：自动检测消息中的网页链接，支持带协议头和无协议头的URL（如 www.example.com）
- **智能内容提取**：使用BeautifulSoup提取网页主要内容
- **LLM智能分析**：集成AstrBot的LLM接口进行深度内容分析
- **网页截图**：自动捕获网页截图，直观展示网页外观，支持多种格式和自定义尺寸
- **异步并发处理**：使用asyncio.gather并发处理多个URL，提高性能
- **高度可配置**：支持多种配置选项，满足不同需求
- **域名控制**：支持允许和禁止域名列表
- **多平台支持**：兼容各种消息平台
- **内容统计**：提供详细的内容统计信息
- **多链接处理**：支持同时处理多条链接，合并成一条合并转发消息发送
- **网页翻译**：支持将网页内容翻译成指定语言
- **结果缓存**：支持分析结果缓存，提高重复请求的响应速度
- **特定内容提取**：支持提取图片、链接、代码块、元信息等特定类型内容
- **缓存管理**：支持查看缓存状态和手动清理缓存
- **分析结果导出**：支持将分析结果导出为Markdown、JSON、TXT等格式，并作为附件发送
- **代理支持**：支持HTTP代理配置，可用于绕过访问限制
- **请求重试机制**：自动重试失败的请求，提高抓取成功率
- **配置验证**：自动验证配置项的有效性，确保插件稳定运行
- **多分析模板**：新增多种LLM分析模板，支持智能模板选择
- **完善的错误处理**：实现错误分级和分类，提供详细的错误信息
- **截图裁剪**：支持自定义截图区域，裁剪指定部分
- **内容哈希缓存**：基于内容哈希的缓存策略，提高缓存命中率
- **缓存预加载**：支持缓存预加载，提高首次访问速度
- **优先级调度**：基于URL优先级的任务调度，提高重要URL的处理速度
- **动态并发**：动态调整并发数，优化资源使用
- **内存监控**：新增内存监控和自动释放机制，延长检查间隔至5分钟
- **浏览器池**：优化浏览器资源管理，实现高效的浏览器实例复用机制，增加定期清理任务
- **多种结果模板**：支持多种结果展示模板，满足不同需求
- **结果折叠**：支持结果折叠功能，优化长文本展示
- **命令补全**：支持命令补全和参数提示功能
- **命令别名自定义**：支持自定义命令别名
- **详细命令帮助**：提供完整的命令帮助系统
- **LLM Tool模式**：新增LLM Tool模式，允许LLM智能决定是否调用analyze_webpage工具
- **URL自动补全**：自动补全URL协议头，处理没有协议头的URL（如www.google.com）
- **URL预处理**：支持URL预处理，去除可能的反引号、空格等
- **URL规范化**：支持URL规范化，确保URL格式一致
- **详细日志记录**：新增详细的日志记录，便于调试和监控
- **LLM自主决策**：新增LLM自主决策功能，允许LLM决定返回分析结果还是截图
- **LLM提示词优化**：为娱乐资讯、体育新闻、教育资讯等多种内容类型添加详细分析模板
- **内容类型检测**：智能检测网页内容类型，支持多种内容类型，提高检测准确性
- **LRU缓存策略**：实现LRU（最近最少使用）缓存策略，提高缓存命中率
- **定期清理机制**：浏览器实例和缓存定期清理，优化资源使用
- **域名统一处理**：将google.com和www.google.com等域名变体视为同一域名，避免重复分析，支持自定义开关

## Star

[![Star History Chart](https://api.star-history.com/svg?repos=Sakura520222/astrbot_plugin_web_analyzer&type=Date)](https://star-history.com/#Sakura520222/astrbot_plugin_web_analyzer&Date)

## 文档

详细文档请查看 [Wiki](wiki/Home.md)：

- [快速开始](wiki/QuickStart.md) - 安装和基本使用指南
- [命令参考](wiki/Commands.md) - 详细的命令说明
- [配置指南](wiki/Configuration.md) - 所有配置项的详细说明
- [技术实现](wiki/TechnicalImplementation.md) - 技术细节和架构
- [常见问题](wiki/FAQ.md) - 常见问题和解决方案
- [开发指南](wiki/Development.md) - 开发相关的信息

## 安装方法

1. 将插件目录复制到AstrBot的插件目录：
   ```bash
   # 目录结构示例
   AstrBot/data/plugins/
   └── astrbot_plugin_web_analyzer/
       ├── main.py
       ├── requirements.txt
       └── ...
   ```

2. 安装依赖：
   ```bash
   # 进入插件目录
   cd AstrBot/data/plugins/astrbot_plugin_web_analyzer
   # 安装依赖
   pip install -r requirements.txt
   ```

3. 重启AstrBot或在WebUI插件管理中点击**重载插件**

## 使用方法

### 自动分析

插件会自动检测消息中的URL链接并进行分析：

```
用户：看看这个新闻 https://example.com/news/article
机器人：检测到网页链接，正在分析: https://example.com/news/article
       [分析结果...]
       [网页截图...]
```

支持无协议头的URL（需在配置中启用）：

```
用户：看看这个新闻 www.example.com/news/article
机器人：检测到网页链接，正在分析: https://www.example.com/news/article
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

支持多种命令别名，方便用户使用：

```
/分析 https://example.com
/总结 https://example.com
/web https://example.com
/analyze https://example.com
```

### 分析模式

插件支持四种分析模式，可通过配置或管理员命令切换：

| 模式 | 说明 |
|------|------|
| auto | 检测到链接自动分析，无需命令（默认模式） |
| manual | 必须使用`/网页分析`命令才会分析，不会自动处理链接 |
| hybrid | 默认自动分析，但管理员可通过命令临时切换 |
| LLMTOOL | 不自动分析链接，让LLM自己决定是否调用analyze_webpage工具 |

**查看当前模式：**
```
/web_mode
```

**切换模式（仅限管理员）：**
```
/web_mode auto      # 切换到自动分析模式
/web_mode manual    # 切换到手动分析模式
/web_mode hybrid    # 切换到混合模式
/web_mode LLMTOOL   # 切换到LLM Tool模式
```

**模式命令别名：**
```
/分析模式
/网页分析模式
```

### 命令帮助

查看所有可用命令和帮助信息：

```
/web_help
```

**命令别名：**
```
/网页分析帮助
/网页分析命令
```

### 配置管理

查看当前插件配置：

```
/web_config
```

**命令别名：**
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

**命令别名：**
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

支持的导出格式：

| 格式 | 说明 |
|------|------|
| md / markdown | Markdown格式，适合阅读和分享 |
| json | JSON格式，适合程序处理和数据交换 |
| txt | 纯文本格式，兼容性好 |

**命令别名：**
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

**命令别名：**
```
/群黑名单
/黑名单
```

## 配置选项

插件支持多种配置选项，可以在AstrBot管理面板中进行设置。以下是主要配置项的说明：

### 核心设置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| analysis_mode | 分析模式，支持auto(自动)、manual(手动)、hybrid(混合)、LLMTOOL(LLM智能决定) | auto |
| enable_no_protocol_url | 识别无协议头URL（如www.example.com） | false |
| default_protocol | 默认协议 | https |
| max_content_length | 最大网页内容长度 | 10000 |
| request_timeout | 请求超时时间(秒) | 30 |
| retry_count | 请求重试次数 | 3 |
| retry_delay | 请求重试间隔(秒) | 2 |
| llm_enabled | 启用LLM智能分析 | true |
| user_agent | 自定义User-Agent | - |
| proxy | HTTP代理配置，格式为http://username:password@host:port，留空表示不使用代理 | - |
| enable_unified_domain | 是否启用域名统一处理（如google.com和www.google.com视为同一域名） | true |

### 域名管理

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| allowed_domains | 允许的域名列表（留空表示允许所有域名） | - |
| blocked_domains | 禁止的域名列表 | - |

### 分析结果配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_emoji | 启用emoji图标 | true |
| enable_statistics | 显示内容统计 | true |
| max_summary_length | 最大摘要长度 | 2000 |
| result_template | 结果展示模板，支持：default, detailed, compact, markdown, simple | default |
| enable_collapsible | 启用结果折叠功能 | false |
| collapse_threshold | 结果折叠阈值 | 1500 |
| enable_llm_decision | 启用LLM自主决策功能 | false |

### 网页截图配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_screenshot | 启用网页截图 | true |
| screenshot_quality | 截图质量（0-100） | 80 |
| screenshot_width | 截图宽度像素 | 1280 |
| screenshot_height | 截图高度像素 | 720 |
| screenshot_format | 截图格式（支持jpeg和png） | jpeg |
| screenshot_full_page | 截取整页 | false |
| screenshot_wait_time | 截图前等待页面加载的时间（毫秒） | 2000 |
| enable_crop | 启用截图裁剪功能 | false |
| crop_area | 裁剪区域，格式为 [left, top, right, bottom] | [0, 0, screenshot_width, screenshot_height] |

### LLM配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| llm_provider | LLM提供商（使用会话默认或指定提供商） | - |
| custom_prompt | 自定义分析提示词 | - |

### 消息管理

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| group_blacklist | 群聊黑名单，在这些群聊中禁用自动分析功能 | - |
| merge_forward_enabled.group | 群聊启用合并转发功能 | false |
| merge_forward_enabled.private | 私聊启用合并转发功能 | false |

### 翻译配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_translation | 启用网页翻译 | false |
| target_language | 目标语言 | zh |
| translation_provider | 翻译提供商 | llm |
| custom_translation_prompt | 自定义翻译提示词 | - |

### 缓存配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_cache | 启用结果缓存 | true |
| cache_expire_time | 缓存过期时间（分钟） | 1440 |
| max_cache_size | 最大缓存数量 | 100 |
| cache_preload_enabled | 启用缓存预加载功能 | false |
| cache_preload_count | 预加载的缓存数量 | 20 |

### 内容提取配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_specific_extraction | 启用特定内容提取 | false |
| extract_types | 提取内容类型，每行一个，支持：title, content, images, links, tables, lists, code, meta | title\ncontent |

## 技术实现

### 核心技术栈

| 功能模块 | 技术实现 |
|----------|----------|
| 异步HTTP请求 | `httpx` |
| HTML解析 | `BeautifulSoup` + `lxml` |
| 网页截图 | `playwright` 无头浏览器 |
| 异步并发 | `asyncio.gather` |
| 缓存机制 | 内存缓存 + 文件缓存 |
| LLM集成 | AstrBot LLM接口 |

### 关键实现细节

#### 网页内容提取
- 智能选择主要内容区域（使用article、main等语义化标签）
- 自动移除脚本和样式标签，只保留纯文本内容
- 支持代理配置，可用于绕过访问限制
- 实现请求重试机制，提高抓取成功率

#### 异步并发处理
- 使用`asyncio.gather`并发处理多个URL
- 优化异步上下文管理器的使用
- 提高多链接处理效率

#### 网页截图
- 支持自定义截图质量、宽度、高度和等待时间
- 支持JPEG和PNG多种格式
- 自动安装浏览器，无需手动配置
- 支持整页截图和自定义区域裁剪

#### 缓存系统
- 双重缓存机制：内存缓存 + 文件缓存
- 支持缓存统计、过期清理和大小限制
- 提供缓存管理命令
- 基于内容哈希的缓存策略，提高缓存命中率

#### LLM分析
- 集成AstrBot的LLM接口
- 提供结构化的分析提示词
- 支持多种分析维度：核心摘要、关键要点、内容类型、价值评估、适用人群
- 支持LLM自主决策模式

#### 配置与错误处理
- 配置验证逻辑，确保配置项有效性
- 详细的配置错误提示
- 网络请求失败时的友好提示
- LLM不可用时的基础分析模式
- 完善的日志记录
- 浏览器自动安装和错误恢复
- 资源的正确释放和清理

## 依赖说明

| 依赖包 | 版本要求 | 用途 |
|--------|----------|------|
| `httpx` | `>=0.24.0` | 异步HTTP客户端 |
| `beautifulsoup4` | `>=4.12.0` | HTML解析库 |
| `lxml` | `>=4.9.0` | 快速XML/HTML解析器 |
| `playwright` | `>=1.40.0` | 浏览器自动化库，用于网页截图 |

## 常见问题

### 截图功能异常

**问题现象**：截图功能不工作或生成的截图异常

**可能原因及解决方法**：
1. **浏览器未正确安装**：插件会自动尝试安装浏览器，若安装失败可手动执行 `playwright install`
2. **网络问题**：请检查网络连接，确保能正常访问目标网站
3. **权限问题**：确保插件有足够的权限创建临时文件
4. **截图格式设置错误**：请确保使用支持的格式（JPEG或PNG）
5. **页面加载问题**：适当增加 `screenshot_wait_time` 配置值

### 分析结果不准确

**问题现象**：网页分析结果与预期不符

**优化建议**：
1. 调整 `max_content_length` 配置，增加抓取的内容长度
2. 调整 `screenshot_wait_time` 配置，增加页面加载等待时间
3. 使用 `custom_prompt` 配置自定义提示词，优化分析结果
4. 检查代理配置是否正确（如果使用了代理）
5. 确保目标网页内容能正常访问

### 插件响应缓慢

**问题现象**：插件处理请求时间过长

**优化建议**：
1. 减少 `max_content_length` 配置，减少抓取的内容长度
2. 关闭 `screenshot_full_page` 选项，只截取可见部分
3. 调整 `request_timeout` 配置，合理设置超时时间
4. 减少 `retry_count` 配置，减少重试次数
5. 根据实际需求考虑关闭 `enable_screenshot` 选项

### 代理配置问题

**问题现象**：配置代理后无法正常使用

**检查要点**：
1. 代理格式是否正确：格式应为 `http://username:password@host:port`
2. 代理服务器是否可用：确保代理服务器能正常访问
3. 代理服务器是否支持HTTPS请求：多数网站使用HTTPS
4. 代理认证信息是否正确：检查用户名和密码

### 缓存功能异常

**问题现象**：缓存不生效或出现异常

**解决方法**：
1. 检查 `enable_cache` 配置是否为 `true`
2. 检查 `cache_expire_time` 配置是否合理（单位：分钟）
3. 尝试使用 `/web_cache clear` 命令手动清理缓存后重新测试
4. 检查缓存目录是否有写入权限
5. 查看日志文件，排查具体错误信息

### 多链接处理问题

**问题现象**：同时发送多个链接时处理异常

**解决方法**：
1. 检查 `merge_forward_enabled` 配置，确保合并转发功能正常
2. 减少单次发送的链接数量
3. 确保服务器资源充足，能支持并发处理

## 开发说明

插件遵循AstrBot插件开发规范：

- 使用中文注释
- 完善的错误处理
- 异步编程模式
- 符合PEP8代码风格

## 开发者联系方式

- GitHub: [https://github.com/Sakura520222](https://github.com/Sakura520222)
- Email: sakura520222@outlook.com

## 许可证

本项目采用 [MIT License](LICENSE) 开源协议。