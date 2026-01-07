# 配置指南

AstrBot 网页分析插件支持多种配置选项，可以在AstrBot管理面板中进行设置。以下是所有配置项的详细说明。

## 核心设置

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

## 域名管理

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| allowed_domains | 允许的域名列表（留空表示允许所有域名） | - |
| blocked_domains | 禁止的域名列表 | - |

## 分析结果配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_emoji | 启用emoji图标 | true |
| enable_statistics | 显示内容统计 | true |
| max_summary_length | 最大摘要长度 | 2000 |
| result_template | 结果展示模板，支持：default, detailed, compact, markdown, simple | default |
| enable_collapsible | 启用结果折叠功能 | false |
| collapse_threshold | 结果折叠阈值 | 1500 |
| enable_llm_decision | 启用LLM自主决策功能 | false |

## 网页截图配置

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

## LLM配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| llm_provider | LLM提供商（使用会话默认或指定提供商） | - |
| custom_prompt | 自定义分析提示词 | - |

## 消息管理

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| group_blacklist | 群聊黑名单，在这些群聊中禁用自动分析功能 | - |
| merge_forward_enabled.group | 群聊启用合并转发功能 | false |
| merge_forward_enabled.private | 私聊启用合并转发功能 | false |

## 翻译配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_translation | 启用网页翻译 | false |
| target_language | 目标语言 | zh |
| translation_provider | 翻译提供商 | llm |
| custom_translation_prompt | 自定义翻译提示词 | - |

## 缓存配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_cache | 启用结果缓存 | true |
| cache_expire_time | 缓存过期时间（分钟） | 1440 |
| max_cache_size | 最大缓存数量 | 100 |
| cache_preload_enabled | 启用缓存预加载功能 | false |
| cache_preload_count | 预加载的缓存数量 | 20 |

## 内容提取配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_specific_extraction | 启用特定内容提取 | false |
| extract_types | 提取内容类型，每行一个，支持：title, content, images, links, tables, lists, code, meta | title
content |

## 配置文件结构

插件的配置文件采用YAML格式，位于AstrBot的数据目录中。配置文件的结构与上述配置项相对应。

## 配置最佳实践

### 性能优化

1. **调整max_content_length**：根据实际需求调整最大网页内容长度，太长会影响性能，太短可能导致内容不完整。
2. **关闭不必要的功能**：如果不需要截图功能，可以关闭`enable_screenshot`选项。
3. **调整截图设置**：关闭`enable_screenshot`或调整截图质量和尺寸可以提高性能。
4. **合理设置缓存**：适当调整缓存过期时间和最大缓存数量，可以提高重复请求的响应速度。

### 准确性优化

1. **增加请求超时**：对于加载较慢的网站，可以适当增加`request_timeout`值。
2. **增加重试次数**：对于不稳定的网络环境，可以适当增加`retry_count`值。
3. **调整截图等待时间**：对于动态加载的网页，可以适当增加`screenshot_wait_time`值。
4. **启用LLM分析**：确保`llm_enabled`为true，以获得更智能的分析结果。

### 安全性优化

1. **设置域名白名单**：在`allowed_domains`中添加允许的域名，可以防止恶意网站的请求。
2. **设置域名黑名单**：在`blocked_domains`中添加禁止的域名，可以屏蔽不需要的网站。
3. **使用代理**：如果需要访问受限网站，可以配置代理服务器。
4. **自定义User-Agent**：使用自定义User-Agent可以减少被目标网站屏蔽的风险。

## 配置示例

以下是一个完整的配置示例：

```yaml
analysis_mode: auto
enable_no_protocol_url: true
default_protocol: https
max_content_length: 20000
request_timeout: 60
retry_count: 5
retry_delay: 3
llm_enabled: true
user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
enable_unified_domain: true

enabled_domains: 
  - "example.com"
  - "google.com"
blocked_domains: 
  - "malicious.com"

enable_emoji: true
enable_statistics: true
max_summary_length: 3000
result_template: detailed
enable_collapsible: true
collapse_threshold: 2000
enable_llm_decision: true

enable_screenshot: true
screenshot_quality: 90
screenshot_width: 1920
screenshot_height: 1080
screenshot_format: png
screenshot_full_page: true
screenshot_wait_time: 5000
enable_crop: false

llm_provider: "default"
custom_prompt: "请详细分析以下网页内容，提供核心摘要、关键要点和价值评估。"

group_blacklist: ["123456789", "987654321"]
merge_forward_enabled:
  group: true
  private: false

enable_translation: true
target_language: "zh"
translation_provider: "llm"

enable_cache: true
cache_expire_time: 2880
max_cache_size: 200
cache_preload_enabled: true
cache_preload_count: 50

enable_specific_extraction: true
extract_types:
  - title
  - content
  - images
  - links
  - code
```

## 配置验证

插件会自动验证配置项的有效性，确保插件稳定运行。如果配置项无效，插件会使用默认值，并在日志中记录警告信息。

## 配置管理命令

可以使用以下命令查看当前配置：

```
/web_config
```

或者使用别名：

```
/网页分析配置
/网页分析设置
```

这些命令会显示当前插件的所有配置项及其值。