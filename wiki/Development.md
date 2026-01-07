# 开发指南

## 插件结构

AstrBot 网页分析插件采用模块化设计，结构清晰，易于扩展和维护。以下是插件的主要文件结构：

```
astrbot_plugin_web_analyzer/
├── main.py                # 插件主入口
├── analyzer.py            # 分析器模块
├── cache.py               # 缓存模块
├── utils.py               # 工具模块
├── metadata.yaml          # 插件元数据
├── _conf_schema.json      # 配置项定义
├── requirements.txt       # 依赖列表
├── README.md              # 插件说明文档
├── CHANGELOG.md           # 更新日志
├── LICENSE                # 许可证
├── logo.png               # 插件图标
└── wiki/                  # 文档目录
    ├── Home.md            # Wiki首页
    ├── QuickStart.md      # 快速开始
    ├── Commands.md        # 命令参考
    ├── Configuration.md   # 配置指南
    ├── TechnicalImplementation.md  # 技术实现
    ├── FAQ.md             # 常见问题
    └── Development.md     # 开发指南
```

## 核心模块说明

### 1. main.py

插件的主入口文件，负责：
- 插件初始化
- 配置加载和验证
- 事件监听和响应
- 命令路由和处理

### 2. analyzer.py

分析器模块，负责：
- 网页内容提取和分析
- LLM调用和结果处理
- 分析结果生成和格式化

### 3. cache.py

缓存模块，负责：
- 内存缓存管理
- 文件缓存管理
- 缓存统计和清理

### 4. utils.py

工具模块，负责：
- URL处理和验证
- 异步HTTP请求
- 网页截图
- 辅助功能和工具函数

## 开发环境搭建

### 1. 安装依赖

```bash
# 克隆代码库
git clone https://github.com/Sakura520222/astrbot_plugin_web_analyzer.git
cd astrbot_plugin_web_analyzer

# 安装依赖
pip install -r requirements.txt
```

### 2. 安装playwright浏览器

```bash
playwright install
```

### 3. 运行测试

目前插件使用AstrBot的测试框架进行测试。请按照AstrBot的测试文档进行测试。

## 开发规范

### 1. 代码风格

- 遵循PEP8代码风格
- 使用4空格缩进
- 变量名使用小写字母加下划线（snake_case）
- 类名使用驼峰命名法（CamelCase）
- 函数名使用小写字母加下划线（snake_case）
- 常量名使用全大写字母加下划线（UPPER_CASE）

### 2. 注释规范

- 使用中文注释
- 函数和类必须有文档字符串
- 复杂逻辑必须添加注释
- 注释应清晰、简洁，说明代码的功能和实现思路

### 3. 异步编程

- 使用async/await语法
- 合理使用异步上下文管理器
- 避免阻塞操作
- 使用asyncio.gather处理并发任务

### 4. 错误处理

- 合理使用try-except捕获异常
- 提供友好的错误信息
- 记录详细的错误日志
- 实现错误分级和分类

## 配置项定义

插件的配置项定义在`_conf_schema.json`文件中，采用JSON Schema格式。每个配置项包含以下信息：

- `name`：配置项名称
- `type`：配置项类型
- `default`：默认值
- `description`：描述
- `required`：是否必填

例如：

```json
{
  "analysis_mode": {
    "type": "string",
    "default": "auto",
    "description": "分析模式，支持auto(自动)、manual(手动)、hybrid(混合)、LLMTOOL(LLM智能决定)",
    "required": false
  }
}
```

## 插件元数据

插件的元数据定义在`metadata.yaml`文件中，包含以下信息：

- `name`：插件名称
- `version`：插件版本
- `description`：插件描述
- `author`：作者信息
- `homepage`：项目主页
- `license`：许可证
- `dependencies`：依赖列表
- `events`：事件监听列表
- `commands`：命令定义列表

## 命令定义

插件的命令定义在`metadata.yaml`文件中，每个命令包含以下信息：

- `name`：命令名称
- `description`：命令描述
- `aliases`：命令别名列表
- `parameters`：参数列表
- `admin_required`：是否需要管理员权限

## 事件处理

插件支持以下事件类型：

- `message`: 消息事件
- `command`: 命令事件
- `plugin_loaded`: 插件加载事件
- `plugin_unloaded`: 插件卸载事件

事件处理函数定义在`main.py`文件中，使用装饰器注册：

```python
@plugin.on("message")
async def on_message(event):
    # 处理消息事件
    pass
```

## 扩展开发

### 1. 添加新功能

1. 分析需求，确定功能模块
2. 在相应的模块中添加代码
3. 更新配置项定义（如果需要）
4. 更新命令定义（如果需要）
5. 更新文档
6. 测试功能

### 2. 自定义分析模板

可以通过修改`analyzer.py`文件中的提示词模板来自定义分析结果：

```python
ANALYSIS_PROMPT_TEMPLATE = """请详细分析以下网页内容，提供：
1. 核心摘要（简洁明了）
2. 关键要点（分点列出）
3. 内容类型
4. 价值评估
5. 适用人群

网页内容：
{content}
"""
```

### 3. 自定义结果模板

可以通过修改`analyzer.py`文件中的结果模板来自定义结果格式：

```python
RESULT_TEMPLATE = """📝 **网页分析结果**

🌐 **URL**: {url}

📊 **内容统计**
- 字符数: {char_count}
- 单词数: {word_count}
- 段落数: {paragraph_count}

📋 **核心摘要**
{summary}

🔍 **关键要点**
{key_points}

📌 **内容类型**: {content_type}
💎 **价值评估**: {value_score}
👥 **适用人群**: {target_audience}
"""
```

## 调试和日志

### 1. 日志配置

插件使用AstrBot的日志系统，默认日志级别为INFO。可以通过配置调整日志级别：

```yaml
logging:
  level: debug
```

### 2. 调试方法

- 使用`logger.debug()`输出调试信息
- 在开发环境中启用DEBUG日志级别
- 使用`asyncio.run()`运行异步函数进行测试

## 测试指南

### 1. 单元测试

使用Python的unittest或pytest框架编写单元测试：

```bash
# 使用pytest运行测试
pytest tests/
```

### 2. 集成测试

将插件安装到AstrBot中进行集成测试：
- 检查插件是否正常加载
- 测试各种命令和功能
- 测试不同配置下的行为
- 测试边界情况和异常情况

### 3. 性能测试

- 测试多链接处理性能
- 测试不同配置下的响应时间
- 测试内存和CPU使用情况

## 发布流程

1. 更新CHANGELOG.md，添加新的更新内容
2. 更新metadata.yaml中的版本号
3. 运行测试，确保所有功能正常
4. 提交代码并推送到GitHub
5. 创建GitHub Release，添加更新说明和下载链接

## 贡献指南

欢迎对插件进行贡献！请遵循以下流程：

1. Fork代码库
2. 创建特性分支
3. 提交代码更改
4. 运行测试
5. 创建Pull Request

### Pull Request要求

- 代码符合开发规范
- 包含必要的测试用例
- 更新相关文档
- 提供清晰的更改描述

## 许可证

本插件采用MIT License开源协议。详见LICENSE文件。

## 技术支持

如果您在开发过程中遇到问题，可以：

- 查看Wiki文档
- 查看常见问题
- 在GitHub上提交Issue
- 联系开发者

## 版本管理

插件使用语义化版本号（Semantic Versioning）：

- 主版本号（MAJOR）：当你做了不兼容的API更改
- 次版本号（MINOR）：当你添加了向后兼容的功能
- 修订号（PATCH）：当你做了向后兼容的bug修复

## 开发计划

### 近期计划

1. 优化网页内容提取算法
2. 支持更多内容类型的分析
3. 增强LLM分析能力
4. 优化性能和资源使用
5. 支持更多导出格式

### 长期计划

1. 支持自定义插件扩展
2. 支持多语言
3. 增强安全性和隐私保护
4. 支持更多平台
5. 提供更丰富的分析报告

## 参考资源

1. [AstrBot插件开发文档](https://github.com/Sakura520222/AstrBot/blob/main/docs/插件开发指南.md)
2. [Python异步编程](https://docs.python.org/3/library/asyncio.html)
3. [BeautifulSoup文档](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
4. [Playwright文档](https://playwright.dev/python/docs/intro)
5. [httpx文档](https://www.python-httpx.org/)

## 开发者联系方式

- GitHub: [https://github.com/Sakura520222](https://github.com/Sakura520222)
- Email: sakura520222@outlook.com

## 致谢

感谢所有为插件开发和维护做出贡献的开发者和用户！