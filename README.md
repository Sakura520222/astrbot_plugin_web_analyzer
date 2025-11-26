# AstrBot 网页分析插件

这是一个AstrBot插件，能够自动识别用户发送的网页链接，抓取网页内容并调用LLM进行分析和总结。

## 功能特性

- 🔍 **自动识别URL**: 自动检测消息中的网页链接
- 📄 **智能内容提取**: 使用BeautifulSoup提取网页主要内容
- 🤖 **LLM智能分析**: 仅使用AstrBot的LLM接口进行深度内容分析
- ⚡ **异步处理**: 使用异步HTTP客户端提高性能

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
```

### 手动分析

使用命令手动分析指定链接：

```
/网页分析 https://example.com
```

## 配置选项

在 `metadata.yaml` 中可以配置以下参数：

```yaml
config:
  # 最大网页内容长度（字符数）
  max_content_length: 10000
  # 请求超时时间（秒）
  request_timeout: 30
  # 是否启用详细日志
  verbose_logging: false
  # LLM配置
  llm_enabled: true  # 是否启用LLM分析（默认启用）
```

## 技术实现

### 网页内容提取

- 使用 `httpx` 进行异步HTTP请求
- 使用 `BeautifulSoup` 和 `lxml` 解析HTML
- 智能选择主要内容区域（article、main等语义化标签）

### LLM分析

- 集成AstrBot的LLM接口
- 提供结构化的分析提示词
- 支持多种分析维度（概述、关键点、类型、价值评估）

### 错误处理

- 网络请求失败时的友好提示
- LLM不可用时的基础分析模式
- 完善的日志记录

## 依赖说明

- `httpx`: 异步HTTP客户端
- `beautifulsoup4`: HTML解析库
- `lxml`: 快速XML/HTML解析器

## 开发说明

插件遵循AstrBot插件开发规范：

- 使用中文注释
- 完善的错误处理
- 异步编程模式
- 符合PEP8代码风格

## 许可证

MIT License