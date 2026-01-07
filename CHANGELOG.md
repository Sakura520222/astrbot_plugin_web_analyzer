# 更新日志

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

## [v1.3.8] - 2026-01-05

### 🎯 代码质量提升与重构
- 重构`_get_error_type`函数：将大量if-elif条件判断改为规则列表，降低循环复杂度，拆分为8个更小的方法，每个方法专注于单一职责
- 重构`detect_content_type`函数：使用内容类型规则列表替代重复的if-elif判断，提高可维护性，拆分为2个更小的方法，分离规则定义和匹配逻辑
- 重构`_handle_error`函数：使用字典映射简化日志记录，优化错误信息生成逻辑，拆分为3个更小的方法，优化错误处理流程
- 重构`_get_param_hints`函数：拆分为4个更小的方法，提高命令提示功能可维护性
- 重构`_load_analysis_settings`函数：优化配置加载逻辑，简化函数结构，拆分为7个更小的方法，每个方法负责一类配置
- 重构`_get_available_commands`函数：拆分为8个更小的方法，每个方法返回一个命令的信息
- 重构`get_url_priority`函数：拆分为`_is_news_domain`、`_is_tech_domain`和`_is_video_domain`三个辅助函数，分离路径和域名优先级计算
- 重构`extract_urls`函数：拆分为5个更小的方法，分离URL提取的不同阶段
- 重构`normalize_url`函数：拆分为2个更小的方法，简化URL规范化逻辑
- 重构`_get_content_type_rules`函数：将返回类型从元组列表改为字典，简化函数结构
- 拆分`_preload_cache`函数：将其拆分为多个辅助函数，每个函数只负责一个具体任务
- 拆分`_release_memory`函数：将浏览器实例池优化提取为独立的异步函数
- 拆分`_cleanup`函数：拆分为`_clean_expired_cache`和`_cleanup_lru_cache`两个辅助函数
- 简化`_save_cache_to_disk`函数：提取截图处理逻辑到单独的`_process_screenshot_for_cache`函数
- 优化`_load_network_settings`函数：拆分为`_load_basic_network_settings`、`_load_concurrency_settings`、`_load_priority_settings`、`_load_url_processing_settings`和`_validate_proxy`五个辅助函数
- 修复代码质量问题：移除未使用的变量和导入，使用ruff --fix修复部分格式化问题
- 使用ruff格式化所有代码，确保代码符合PEP 8规范
- 提高代码的可读性和可维护性

## [v1.3.7] - 2026-01-04

### 🐛 Bug修复
- 修复LLM工具调用失败问题：完善工具方法文档字符串，确保@filter.llm_tool装饰器能正确生成参数定义
- 修复analyze_webpage_tool函数参数解析问题，添加详细的Args文档
- 修复analyze_webpage_with_decision_tool函数参数解析问题，添加详细的Args文档

## [v1.3.6] - 2026-01-03

### ✨ 功能增强
- 浏览器实例池管理优化：实现高效的浏览器实例复用机制，增加定期清理任务，限制最大实例数量
- 内存监控机制改进：延长检查间隔至5分钟，优化内存释放策略，增强容错机制
- 缓存策略优化：实现LRU缓存，添加内容哈希到URL的映射，优化缓存清理机制
- 错误处理机制增强：完善错误类型枚举，增强处理逻辑，改进日志记录
- LLM提示词改进：为娱乐资讯、体育新闻、教育资讯等新内容类型添加详细模板
- 内容类型检测算法改进：支持更多内容类型，提高检测准确性
- 域名统一处理功能：修复google.com和www.google.com等域名变体的重复分析问题，实现可自定义的域名统一处理

### 🔄 性能优化
- 优化并发处理机制，支持动态调整并发数
- 改进URL处理优先级评估，确保重要URL优先处理
- 增强批量URL处理效率，支持分批次处理

### 🎯 代码质量提升
- 代码结构优化：将复杂方法拆分为多个独立功能的小方法，重构_process_single_url方法
- 代码风格统一：使用ruff工具检查和修复422个代码风格问题，确保代码符合PEP 8规范
- 完善代码注释，增强代码的可理解性

### ⚙️ 配置调整
- 浏览器实例池配置：设置最大实例数量为3，清理间隔为5分钟，实例超时时间为30分钟
- 内存检查间隔从60秒延长到5分钟，降低性能开销
- 实现基于内存使用情况的动态浏览器实例数量调整
- 新增enable_unified_domain配置项，支持自定义是否启用域名统一处理功能
- 在_conf_schema.json中添加enable_unified_domain配置，支持通过AstrBot管理面板进行配置

## [v1.3.5] - 2025-12-27

### ✨ 功能增强
- 新增LLM自主决策功能，允许LLM决定返回分析结果还是截图
- 实现`analyze_webpage_with_decision`函数工具，支持指定返回内容类型
- 支持三种返回类型：`analysis_only`（仅分析结果）、`screenshot_only`（仅截图）、`both`（两者都返回）

### ⚙️ 配置调整
- 新增`enable_llm_decision`配置项，用于控制是否启用LLM自主决策功能
- 将`enable_llm_decision`配置项添加到`analysis_settings`中，使其与分析相关配置更集中

## [v1.3.4] - 2025-12-26

### ✨ 功能增强
- 新增LLM Tool模式，将其合并到analysis_mode配置中
- 当analysis_mode设置为LLMTOOL时，不自动分析链接，让LLM自己决定是否调用analyze_webpage工具
- 当analysis_mode为其他值时，使用对应模式的解析方式
- 注册analyze_webpage工具，供LLM自行调用
- 支持自动补全URL协议头，处理没有协议头的URL（如www.google.com）
- 支持URL预处理，去除可能的反引号、空格等
- 支持URL规范化，确保URL格式一致
- 新增详细的日志记录，便于调试和监控
- 当未启用LLMTOOL模式时，拒绝analyze_webpage工具调用

### ⚙️ 配置调整
- 将LLM Tool模式合并到analysis_mode配置中，新增LLMTOOL选项
- 移除llm_tool_settings配置项和enable_llm_tool配置开关
- 分析模式现在包含四个选项：auto(自动)、manual(手动)、hybrid(混合)、LLMTOOL(LLM智能决定)
- 当analysis_mode为LLMTOOL时，不自动分析链接，让LLM自己决定

## [v1.3.3] - 2025-12-25

### ✨ 功能增强
- 新增分析模式功能，支持自动分析、手动分析和混合模式三种模式
- 新增 analysis_mode 配置项，可在配置中选择分析模式
- 新增 /web_mode 管理员命令，支持动态切换分析模式
- 支持命令别名：/分析模式、/网页分析模式
- 在 manual 模式下，必须使用 /网页分析 命令才会分析链接
- 在 auto 模式下，自动检测并分析消息中的链接
- 在 hybrid 模式下，默认自动分析，管理员可通过命令临时切换
- 优化 auto_detect_urls 方法，支持根据分析模式控制自动分析行为
- 更新 /web_config 命令，显示当前分析模式

### ⚙️ 配置调整
- 新增 analysis_mode 配置项，支持 auto、manual、hybrid 三种模式
- auto_analyze 配置项标记为已废弃，建议使用 analysis_mode 配置
- 保持向后兼容，支持旧的 auto_analyze 配置项

## [v1.3.2] - 2025-12-23

### 🐛 Bug修复
- 修复无协议头URL识别时重复匹配的问题，当消息中包含带协议头的URL时，避免将URL中的域名部分再次识别为无协议头URL

## [v1.3.1] - 2025-12-23

### ✨ 功能增强
- 新增无协议头URL识别功能，支持识别不包含协议头的URL（如 www.example.com 或 example.com）
- 新增 enable_no_protocol_url 配置项，可控制是否启用无协议头URL识别
- 新增 default_protocol 配置项，可设置无协议头URL使用的默认协议（http或https）

### 🐛 Bug修复
- 改进无协议头URL正则表达式，要求域名每部分至少2个字符，避免匹配无效域名（如 cn.nd）
- 优化分析结果发送逻辑，当所有URL都分析失败时不发送消息，避免发送错误提示

## [v1.3.0] - 2025-12-22

### ✨ 功能增强
- 实现智能撤回功能，将原有的定时撤回升级为支持智能撤回
- 智能撤回模式下，分析完成后立即撤回处理中消息，提升用户体验
- 支持配置撤回类型：time_based(定时撤回)或smart(智能撤回)
- 新增smart_recall_enabled配置项，可独立控制是否启用智能撤回

### ⚙️ 配置调整
- 新增recall_type配置项，支持选择撤回类型
- 新增smart_recall_enabled配置项，控制智能撤回功能
- 默认撤回类型设为智能撤回

## [v1.2.9] - 2025-12-21

### 🐛 Bug修复
- 修复浏览器实例池管理问题，当浏览器实例无效时自动创建新实例
- 解决 `Browser.new_page: Target page, context or browser has been closed` 错误
- 提高截图功能的稳定性和可靠性

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

## [v1.2.7] - 2025-12-14

### ✨ 功能增强
- 新增自动撤回正在分析提醒消息功能，提升用户体验
- 添加 `recall_settings` 配置项，支持控制是否启用自动撤回及撤回延迟时间

## [v1.2.6] - 2025-12-13

### 🔒 权限控制
- 将缓存管理指令（`web_cache`、`网页缓存`、`清理缓存`）改为仅管理员可用

## [v1.2.5] - 2025-12-12

### 🔄 性能优化
- `main.py` 中 `_extract_specific_content` 方法避免重复创建 `WebAnalyzer` 实例
- `analyzer.py` 中 `capture_screenshot` 方法添加浏览器安装检查缓存，避免每次截图都执行安装命令
- 所有URL在使用前进行规范化处理，提高缓存清理效率，避免重复分析
- 在分析网页前对URL进行去重处理，减少重复分析，提高响应速度

### 🐛 Bug修复
- `main.py` 中 `export_analysis_result` 方法修复不存在的 `self.cache` 属性引用
- `cache.py` 中移除两个未使用的 `has_screenshot` 变量
- `analyzer.py` 中修复网页解析时 `'NoneType' object is not callable` 错误
- 修复BeautifulSoup API使用错误：移除`element.copy()`调用，直接处理原始元素，提高解析健壮性

### 🎯 代码质量提升
- `cache.py` 中 `__init__` 方法确保 `cache_dir` 参数正确初始化

### � 功能优化
- 新增 `normalize_url` 方法，统一处理URL格式，解决缓存清理后仍使用缓存的问题
- `analyzer.py` 中 `fetch_webpage` 方法添加完整浏览器请求头，解决403 Forbidden问题

## [v1.2.4] - 2025-12-07

### 🔄 功能优化
- 合并转发功能优化：支持群聊和私聊单独设置
- 合并转发包含截图：新增 `include_screenshot` 配置选项，支持将截图合并到转发消息中
- 发送内容类型自定义：新增 `send_content_type` 配置选项，允许选择发送分析结果、截图或两者都发送

### ⚙️ 配置调整
- 将 `merge_forward_enabled` 改为对象类型，新增 `group` 和 `private` 子配置
- 将所有配置项重新分组为9个类别，包括网络设置、域名管理、分析设置等，使配置结构更清晰

## [v1.0.0 - v1.2.3] - 2025-12-05

### 功能特性
- 🔍 自动识别URL功能
- 📄 智能内容提取
- 🤖 LLM智能分析
- 📸 网页截图功能
- ⚡ 异步并发处理
- 🎨 高度可配置选项
- 🔒 域名控制
- 📱 多平台支持
- 📊 内容统计
- 🔗 多链接处理
- 🌐 网页翻译
- 📦 结果缓存
- 🎯 特定内容提取
- 🧹 缓存管理
- 💾 分析结果导出
- 🕵️ 代理支持
- 🔄 请求重试机制
- ✅ 配置验证
- 支持合并转发功能
- 新增了多种命令别名
- 支持自定义截图格式和尺寸
