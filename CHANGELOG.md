# 更新日志

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
