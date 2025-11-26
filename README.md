# AstrBot 网页分析插件

这是一个AstrBot插件，能够自动识别用户发送的网页链接，抓取网页内容并调用LLM进行分析和总结，同时支持网页截图功能。

## 功能特性

- 🔍 **自动识别URL**: 自动检测消息中的网页链接
- 📄 **智能内容提取**: 使用BeautifulSoup提取网页主要内容
- 🤖 **LLM智能分析**: 集成AstrBot的LLM接口进行深度内容分析
- 📸 **网页截图**: 自动捕获网页截图，直观展示网页外观
- ⚡ **异步处理**: 使用异步HTTP客户端提高性能
- 🎨 **可配置**: 支持多种配置选项，满足不同需求
- 🔒 **域名控制**: 支持允许和禁止域名列表
- 📱 **多平台支持**: 兼容各种消息平台
- 📊 **内容统计**: 提供详细的内容统计信息

## 安装方法

1. 将插件目录复制到AstrBot的插件目录：
   ```bash
   cp -r astrbot_plugin_web_analyzer /AstrBot/data/plugins/
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

### 手动分析

使用命令手动分析指定链接：

```
/网页分析 https://example.com
```

### 命令别名

支持以下命令别名：

```
/分析 https://example.com
/总结 https://example.com
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

## 配置选项

插件支持多种配置选项，可以在AstrBot管理面板中进行设置：

### 基本设置

- **max_content_length**: 最大网页内容长度（默认：10000）
- **request_timeout**: 请求超时时间(秒)（默认：30）
- **llm_enabled**: 启用LLM智能分析（默认：true）
- **auto_analyze**: 自动分析检测到的链接（默认：true）
- **user_agent**: 自定义User-Agent

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
- **screenshot_full_page**: 截取整页（默认：false）
- **screenshot_wait_time**: 截图前等待页面加载的时间（毫秒，默认：2000）

### LLM配置

- **llm_provider**: LLM提供商（使用会话默认或指定提供商）
- **custom_prompt**: 自定义分析提示词

### 群聊控制

- **group_blacklist**: 群聊黑名单，在这些群聊中禁用自动分析功能

### 合并转发

- **merge_forward_enabled**: 启用合并转发功能（仅群聊有效，默认：false）

## 技术实现

### 网页内容提取

- 使用 `httpx` 进行异步HTTP请求
- 使用 `BeautifulSoup` 和 `lxml` 解析HTML
- 智能选择主要内容区域（article、main等语义化标签）
- 移除脚本和样式标签，只保留纯文本内容

### 网页截图

- 使用 `playwright` 进行无头浏览器截图
- 支持自定义截图质量、宽度和等待时间
- 自动安装浏览器，无需手动配置

### LLM分析

- 集成AstrBot的LLM接口
- 提供结构化的分析提示词
- 支持多种分析维度：
  - 核心摘要
  - 关键要点
  - 内容类型
  - 价值评估
  - 适用人群

### 错误处理

- 网络请求失败时的友好提示
- LLM不可用时的基础分析模式
- 完善的日志记录
- 浏览器自动安装和错误恢复

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

### 分析结果不准确

如果分析结果不准确，可以尝试：

1. 调整 `max_content_length` 配置，增加抓取的内容长度
2. 调整 `screenshot_wait_time` 配置，增加页面加载等待时间
3. 使用自定义提示词，优化分析结果

### 插件响应缓慢

如果插件响应缓慢，可以尝试：

1. 减少 `max_content_length` 配置，减少抓取的内容长度
2. 关闭 `screenshot_full_page` 选项，只截取可见部分
3. 调整 `request_timeout` 配置，减少超时时间

## 开发说明

插件遵循AstrBot插件开发规范：

- 使用中文注释
- 完善的错误处理
- 异步编程模式
- 符合PEP8代码风格

## 许可证

MIT License