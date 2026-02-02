# main.py 重构说明文档

## 概述

本文档说明了 main.py 的模块化重构工作。原始 main.py 文件超过 3000 行代码，违反了 Python 开发规范中关于代码组织和可维护性的要求。

## 重构目标

遵循 Python 开发规范（PEP 8），将代码按照功能模块进行拆分，提高代码的可维护性和可读性。

## 新增文件结构

```
astrbot_plugin_web_analyzer/
├── core/                          # 核心模块目录（新增）
│   ├── __init__.py               # 模块初始化
│   ├── constants.py              # 常量和枚举定义
│   ├── error_handler.py          # 错误处理逻辑
│   ├── config_loader.py          # 配置加载逻辑
│   ├── result_formatter.py       # 结果格式化逻辑
│   ├── llm_analyzer.py           # LLM 分析逻辑（新增）
│   └── message_handler.py        # 消息处理逻辑（新增）
├── main.py                        # 原始主文件（保留）
├── main_refactored.py             # 完整重构版本（新增）
├── main_new.py                    # 简化重构版本示例
├── analyzer.py                    # 网页分析器（原有）
├── cache.py                       # 缓存管理（原有）
├── utils.py                       # 工具函数（原有）
└── REFACTORING.md                 # 本文档
```

## 核心模块说明

### 1. core/constants.py

**功能**：定义所有常量、枚举和配置字典

**主要内容**：
- `ErrorType`：错误类型枚举
- `ErrorSeverity`：错误严重程度枚举
- `ERROR_MESSAGES`：错误消息配置字典

**使用示例**：
```python
from core.constants import ErrorType, ErrorSeverity, ERROR_MESSAGES

error_type = ErrorType.NETWORK_ERROR
severity = ErrorSeverity.ERROR
```

### 2. core/error_handler.py

**功能**：提供统一的错误处理和日志记录

**主要内容**：
- `ErrorHandler` 类：错误处理器
  - `handle_error()`: 统一错误处理方法
  - `get_error_type()`: 根据异常获取错误类型
  - 各种私有方法用于检测不同类型的错误

**使用示例**：
```python
from core.error_handler import ErrorHandler

error_msg = ErrorHandler.handle_error(
    error_type=ErrorType.NETWORK_ERROR,
    original_error=e,
    url=url
)
```

### 3. core/config_loader.py

**功能**：加载、验证和初始化所有配置项

**主要内容**：
- `ConfigLoader` 类：配置加载器
  - `load_all_config()`: 加载所有配置项
  - 各种私有方法用于加载不同类型的配置

**使用示例**：
```python
from core.config_loader import ConfigLoader

config_dict = ConfigLoader.load_all_config(config, context)
for key, value in config_dict.items():
    setattr(self, key, value)
```

### 4. core/result_formatter.py

**功能**：格式化分析结果、应用模板、折叠长内容

**主要内容**：
- `ResultFormatter` 类：结果格式化器
  - `apply_result_settings()`: 应用所有结果设置
  - `build_enhanced_analysis()`: 构建增强版基础分析
  - 各种私有方法用于不同的格式化需求

**使用示例**：
```python
from core.result_formatter import ResultFormatter

formatter = ResultFormatter(
    enable_emoji=True,
    enable_statistics=True
)
result = formatter.apply_result_settings(
    result=analysis_result,
    url=url,
    content_data=content_data,
    enable_custom_template=self.enable_custom_template,
    result_template=self.result_template
)
```

### 5. core/llm_analyzer.py（新增）

**功能**：调用大语言模型进行智能内容分析和总结

**主要内容**：
- `LLMAnalyzer` 类：LLM 分析器
  - `check_llm_availability()`: 检查 LLM 是否可用
  - `get_llm_provider()`: 获取合适的 LLM 提供商
  - `build_llm_prompt()`: 构建优化的 LLM 提示词
  - `analyze_with_llm()`: 调用 LLM 进行分析
  - `format_llm_result()`: 格式化 LLM 返回结果
  - `_detect_content_type()`: 智能检测内容类型
  - `_get_analysis_template()`: 根据内容类型获取分析模板

**使用示例**：
```python
from core.llm_analyzer import LLMAnalyzer

llm_analyzer = LLMAnalyzer(
    context=context,
    llm_provider=self.llm_provider,
    custom_prompt=self.custom_prompt,
    max_summary_length=self.max_summary_length,
    enable_emoji=self.enable_emoji
)
result = await llm_analyzer.analyze_with_llm(event, content_data)
```

### 6. core/message_handler.py（新增）

**功能**：处理单个和批量 URL 分析、发送分析结果

**主要内容**：
- `MessageHandler` 类：消息处理器
  - `check_cache()`: 检查 URL 缓存
  - `update_cache()`: 更新 URL 缓存
  - `process_single_url()`: 处理单个 URL
  - `send_analysis_result()`: 发送分析结果
  - 各种私有方法用于内容抓取、提取、分析等

**使用示例**：
```python
from core.message_handler import MessageHandler

message_handler = MessageHandler(
    analyzer=self.analyzer,
    cache_manager=self.cache_manager,
    enable_cache=self.enable_cache,
    enable_screenshot=self.enable_screenshot,
    send_content_type=self.send_content_type,
    screenshot_format=self.screenshot_format
)
result = await message_handler.process_single_url(
    event=event,
    url=url,
    analyzer=self.analyzer,
    llm_analyzer=self.llm_analyzer
)
```

## 使用方法

### 方式一：逐步迁移（推荐）

1. **保留原始 main.py**，添加对新模块的导入：

```python
# 在 main.py 顶部添加导入
from core.constants import ErrorType, ErrorSeverity, ERROR_MESSAGES
from core.error_handler import ErrorHandler
from core.config_loader import ConfigLoader
from core.result_formatter import ResultFormatter
from core.llm_analyzer import LLMAnalyzer
from core.message_handler import MessageHandler
```

2. **逐步替换方法实现**：

```python
# 替换初始化方法
def __init__(self, context, config):
    super().__init__(context)
    self.config = config
    
    # 使用配置加载器
    config_dict = ConfigLoader.load_all_config(config, context)
    for key, value in config_dict.items():
        setattr(self, key, value)
    
    # 初始化核心组件
    self._init_components(context, config_dict)

# 添加组件初始化方法
def _init_components(self, context, config_dict):
    self.cache_manager = CacheManager(...)
    self.analyzer = WebAnalyzer(...)
    self.result_formatter = ResultFormatter(...)
    self.llm_analyzer = LLMAnalyzer(...)
    self.message_handler = MessageHandler(...)
```

3. **测试每个修改**，确保功能正常

### 方式二：使用完整重构版本

直接参考 `main_refactored.py`，这是一个完整的、可用的重构版本：

```python
# main_refactored.py 的主要特点：
# 1. 使用所有核心模块
# 2. 代码简洁清晰（约300行 vs 原始3000行）
# 3. 完整的功能实现
# 4. 符合 PEP 8 规范
# 5. 易于维护和扩展
```

### 方式三：使用简化版本

参考 `main_new.py`，这是一个简化版本，展示核心用法：

```python
# main_new.py 适合：
# 1. 学习如何使用核心模块
# 2. 理解模块之间的关系
# 3. 作为自定义开发的起点
```

## 重构前后对比

### 代码行数对比

| 文件 | 行数 | 说明 |
|------|------|------|
| 原始 main.py | 3000+ | 单一文件，所有逻辑混在一起 |
| core/constants.py | ~200 | 常量和枚举定义 |
| core/error_handler.py | ~250 | 错误处理逻辑 |
| core/config_loader.py | ~450 | 配置加载逻辑 |
| core/result_formatter.py | ~350 | 结果格式化逻辑 |
| core/llm_analyzer.py | ~300 | LLM 分析逻辑 |
| core/message_handler.py | ~250 | 消息处理逻辑 |
| main_refactored.py | ~300 | 主入口文件，清晰简洁 |
| **总计** | ~2100 | 模块化，易于维护 |

### 优势对比

| 方面 | 重构前 | 重构后 |
|------|--------|--------|
| 代码组织 | 单一文件3000+行 | 7个模块，职责明确 |
| 可维护性 | 低，修改困难 | 高，模块独立 |
| 可测试性 | 低，耦合严重 | 高，模块可独立测试 |
| 可扩展性 | 低，牵一发动全身 | 高，新功能独立模块 |
| 代码复用 | 低，代码重复 | 高，通用模块可复用 |
| 团队协作 | 难，冲突频繁 | 易，模块并行开发 |

## 模块依赖关系

```
main_refactored.py (主入口)
    ├─→ ConfigLoader (配置加载)
    ├─→ ErrorHandler (错误处理)
    ├─→ ResultFormatter (结果格式化)
    ├─→ LLMAnalyzer (LLM 分析)
    │       └─→ ResultFormatter
    ├─→ MessageHandler (消息处理)
    │       ├─→ ErrorHandler
    │       ├─→ CacheManager
    │       ├─→ WebAnalyzer
    │       └─→ LLMAnalyzer
    └─→ WebAnalyzer (网页分析)
```

## 代码规范遵循

重构后的代码严格遵循以下规范：

✅ **项目结构规范**
- 所有模块存放在 `core/` 目录
- `main.py` 作为唯一入口文件

✅ **导入规范**
- 按标准库、第三方库、本地库分组
- 使用绝对导入
- 一行只导入一个模块

✅ **命名规范**
- 类名使用 PascalCase
- 函数和变量使用 snake_case
- 常量使用 UPPER_CASE

✅ **注释规范**
- 所有公共模块、类、函数都有文档字符串
- 使用 Google 风格的文档字符串
- 复杂逻辑有行内注释

✅ **代码布局**
- 使用 4 个空格缩进
- 每行不超过 79 个字符
- 适当的空行分隔代码块

## 迁移指南

### 步骤1：备份原始文件

```bash
cp main.py main_backup.py
```

### 步骤2：测试核心模块

```python
# 在 Python 交互环境测试
from core.constants import ErrorType
from core.error_handler import ErrorHandler
from core.config_loader import ConfigLoader
# 确认所有模块可以正常导入
```

### 步骤3：逐步迁移功能

1. 先迁移配置加载逻辑
2. 再迁移错误处理逻辑
3. 然后迁移结果格式化逻辑
4. 最后迁移 LLM 和消息处理逻辑

### 步骤4：完整测试

- 单元测试：测试每个模块
- 集成测试：测试模块间协作
- 功能测试：测试所有原有功能
- 性能测试：确保性能未下降

### 步骤5：部署上线

```bash
# 备份当前版本
cp main.py main_old.py

# 使用重构版本
cp main_refactored.py main.py

# 重启 AstrBot
```

## 测试建议

1. **单元测试**：为每个核心模块编写单元测试
2. **集成测试**：测试模块之间的协作
3. **功能测试**：确保所有原有功能正常工作
4. **性能测试**：确保重构后性能没有下降

## 注意事项

1. **向后兼容**：确保重构后的代码与现有配置和数据格式兼容
2. **错误处理**：保持原有的错误处理逻辑不变
3. **日志记录**：保留所有重要的日志记录
4. **配置迁移**：如有配置格式变化，提供迁移方案
5. **逐步迁移**：建议先在测试环境验证，再逐步迁移到生产环境

## 常见问题

### Q1: 如何添加新的错误类型？

在 `core/constants.py` 的 `ErrorType` 枚举中添加：

```python
class ErrorType(str, Enum):
    NETWORK_ERROR = "network_error"
    # 添加新类型
    NEW_ERROR_TYPE = "new_error_type"
```

然后在 `ERROR_MESSAGES` 中配置消息。

### Q2: 如何自定义 LLM 提示词？

有两种方式：

1. 通过配置文件设置 `custom_prompt`
2. 在代码中修改 `_get_analysis_template()` 方法

### Q3: 如何添加新的消息处理逻辑？

在 `MessageHandler` 类中添加新方法，或在 `main_refactored.py` 中扩展。

## 参考资源

- [PEP 8 -- Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [AstrBot 插件开发文档](./Astrbot插件开发文档.md)
- [Python 开发全量规范](../../.clinerules/python开发规范.md)

## 更新日志

### v1.0.0 (2024-02-02)
- ✅ 创建 core 模块目录
- ✅ 拆分常量和错误处理模块
- ✅ 拆分配置加载模块
- ✅ 拆分结果格式化模块
- ✅ 创建 LLM 分析模块
- ✅ 创建消息处理模块
- ✅ 完成完整重构版本 main_refactored.py
- ✅ 编写详细的重构说明文档

## 联系方式

如有问题或建议，请联系项目维护者。