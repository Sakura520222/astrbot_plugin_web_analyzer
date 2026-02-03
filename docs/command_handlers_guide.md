# command_handlers.py 模块使用指南

## 概述

`core/command_handlers.py` 是一个包含所有插件命令处理逻辑的模块，旨在将命令处理方法从主类中分离出来，提高代码的可维护性和可读性。

## 当前状态

**注意**：由于 AstrBot 框架的 `@filter.command` 装饰器无法识别通过 Mixin 继承的方法，因此该模块目前**无法直接通过 Mixin 模式使用**。

所有命令处理方法已直接定义在 `main.py` 的主类中，以确保命令能够正确注册和执行。

## 模块结构

```python
class CommandMixin:
    """命令处理方法的 Mixin 类（用于代码组织参考）"""
    
    # 命令处理方法列表
    - show_help()              # 显示帮助信息
    - show_config()            # 显示配置信息
    - test_merge_forward()     # 测试合并转发
    - manage_group_blacklist() # 管理群聊黑名单
    - manage_cache()           # 管理缓存
    - manage_analysis_mode()   # 管理分析模式
    - export_analysis_result() # 导出分析结果
    
    # 辅助方法
    - _save_group_blacklist()  # 保存群聊黑名单
    - _translate_content()     # 翻译内容
    - _add_specific_content_to_result() # 添加特定内容到结果
    - _batch_process_urls()    # 批量处理URL
```

## 为什么无法直接使用？

### 技术原因

在 Python 中，使用 `@filter.command` 装饰器时，AstrBot 框架会在类定义时扫描并注册命令。当方法通过 Mixin 继承时：

```python
# 主类
class WebAnalyzerPlugin(Star, CommandMixin):
    pass

# 框架扫描时的问题：
# 1. 装饰器在 CommandMixin 类定义时执行
# 2. 但框架只识别 WebAnalyzerPlugin 主类的装饰器
# 3. 继承的方法装饰器信息丢失
```

### 实际测试结果

```python
# 测试命令是否注册
from core.command_handlers import CommandMixin
methods = [m for m in dir(CommandMixin) if not m.startswith('_')]
print("CommandMixin 中的公共方法:", methods)
# 输出: 所有方法都存在，但装饰器未生效
```

## 如何使用该模块

### 方式一：作为代码参考

该模块可以作为重构 `main.py` 中的命令处理逻辑的参考：

```python
# 从 main.py 中复制命令处理逻辑
@filter.command("web_help", alias={"网页分析帮助", "网页分析命令"})
async def show_help(self, event: AstrMessageEvent):
    """显示插件的所有可用命令和帮助信息"""
    # 参考 command_handlers.py 中的实现
    help_text = """..."""
    yield event.plain_result(help_text)
```

### 方式二：手动迁移方法

如果将来框架支持或者找到解决方案，可以按以下步骤迁移：

#### 步骤 1：准备命令处理方法

```python
# core/command_handlers.py

class WebCommandHandlers:
    """独立的命令处理器类"""
    
    def __init__(self, plugin_instance):
        """保存插件实例引用"""
        self.plugin = plugin_instance
    
    # 注意：这些方法不带装饰器
    async def handle_show_help(self, event: AstrMessageEvent):
        """处理帮助命令"""
        help_text = """..."""
        yield event.plain_result(help_text)
    
    async def handle_show_config(self, event: AstrMessageEvent):
        """处理配置查看命令"""
        config_info = f"""..."""
        yield event.plain_result(config_info)
```

#### 步骤 2：在主类中注册

```python
# main.py

from core.command_handlers import WebCommandHandlers

class WebAnalyzerPlugin(Star):
    
    def __init__(self, context, config):
        # 初始化命令处理器
        self.cmd_handlers = WebCommandHandlers(self)
    
    # 装饰器注册命令
    @filter.command("web_help", alias={"网页分析帮助"})
    async def show_help(self, event):
        # 委托给命令处理器
        async for result in self.cmd_handlers.handle_show_help(event):
            yield result
```

### 方式三：动态注册（实验性）

如果框架支持动态命令注册：

```python
# main.py

class WebAnalyzerPlugin(Star):
    
    def __init__(self, context, config):
        super().__init__(context)
        self._register_commands_from_handler()
    
    def _register_commands_from_handler(self):
        """动态从命令处理器注册命令"""
        from core.command_handlers import WebCommandHandlers
        
        handler = WebCommandHandlers(self)
        
        # 遍历处理器的方法并注册
        for method_name in dir(handler):
            if method_name.startswith('handle_'):
                # 注册命令（需要框架支持）
                self._register_command(method_name, getattr(handler, method_name))
```

## 命令方法详细说明

### 1. show_help()

显示插件的所有可用命令和帮助信息。

```python
@filter.command("web_help", alias={"网页分析帮助", "网页分析命令"})
async def show_help(self, event: AstrMessageEvent):
    """显示插件的所有可用命令和帮助信息"""
    help_text = """..."""
    yield event.plain_result(help_text)
```

**命令别名**: `web_help`, `网页分析帮助`, `网页分析命令`  
**返回**: 帮助文本信息

### 2. show_config()

显示当前插件的详细配置信息。

```python
@filter.command("web_config", alias={"网页分析配置", "网页分析设置"})
async def show_config(self, event: AstrMessageEvent):
    """显示当前插件的详细配置信息"""
    config_info = f"""..."""
    yield event.plain_result(config_info)
```

**命令别名**: `web_config`, `网页分析配置`, `网页分析设置`  
**返回**: 配置信息文本

### 3. test_merge_forward()

测试合并转发功能。

```python
@filter.command("test_merge", alias={"测试合并转发", "测试转发"})
async def test_merge_forward(self, event: AstrMessageEvent):
    """测试合并转发功能"""
    # 创建测试节点并发送
```

**命令别名**: `test_merge`, `测试合并转发`, `测试转发`  
**限制**: 仅支持群聊消息

### 4. manage_group_blacklist()

管理群聊黑名单。

```python
@filter.command("group_blacklist", alias={"群黑名单", "黑名单"})
async def manage_group_blacklist(self, event: AstrMessageEvent):
    """管理群聊黑名单"""
    # 解析命令参数
    message_parts = event.message_str.strip().split()
    
    action = message_parts[1].lower() if len(message_parts) > 1 else ""
    group_id = message_parts[2] if len(message_parts) > 2 else ""
    
    # 处理操作: add, remove, clear
```

**命令别名**: `group_blacklist`, `群黑名单`, `黑名单`  
**操作类型**:
- `add <群号>`: 添加群聊到黑名单
- `remove <群号>`: 从黑名单移除群聊
- `clear`: 清空黑名单

**示例**:
```
/group_blacklist add 123456789
/group_blacklist remove 123456789
/group_blacklist clear
```

### 5. manage_cache()

管理插件的网页分析结果缓存（需要管理员权限）。

```python
@filter.permission_type(filter.PermissionType.ADMIN)
@filter.command("web_cache", alias={"网页缓存", "清理缓存"})
async def manage_cache(self, event: AstrMessageEvent):
    """管理插件的网页分析结果缓存"""
    # 显示缓存状态或清空缓存
```

**命令别名**: `web_cache`, `网页缓存`, `清理缓存`  
**权限**: 需要管理员权限  
**操作类型**:
- 无参数: 显示当前缓存状态
- `clear`: 清空所有缓存

**示例**:
```
/web_cache
/web_cache clear
```

### 6. manage_analysis_mode()

管理插件的网页分析模式（需要管理员权限）。

```python
@filter.permission_type(filter.PermissionType.ADMIN)
@filter.command("web_mode", alias={"分析模式", "网页分析模式"})
async def manage_analysis_mode(self, event: AstrMessageEvent):
    """管理插件的网页分析模式"""
    # 显示或切换分析模式
```

**命令别名**: `web_mode`, `分析模式`, `网页分析模式`  
**权限**: 需要管理员权限  
**支持模式**:
- `auto`: 自动分析模式
- `manual`: 手动分析模式
- `hybrid`: 混合模式
- `LLMTOOL`: LLM工具模式

**示例**:
```
/web_mode auto
/web_mode LLMTOOL
```

### 7. export_analysis_result()

导出网页分析结果。

```python
@filter.command("web_export", alias={"导出分析结果", "网页导出"})
async def export_analysis_result(self, event: AstrMessageEvent):
    """导出网页分析结果"""
    # 支持导出单个URL或所有缓存结果
    # 支持格式: md, json, txt
```

**命令别名**: `web_export`, `导出分析结果`, `网页导出`  
**参数**:
- 第一个参数: URL 或 `all`（导出所有）
- 第二个参数: 格式类型（md, json, txt）

**示例**:
```
/web_export https://example.com md
/web_export all json
/web_export https://example.com txt
```

## 辅助方法说明

### _save_group_blacklist()

将群聊黑名单保存到配置文件。

```python
def _save_group_blacklist(self):
    """保存群聊黑名单到配置文件"""
    # 将列表转换为文本并保存
```

### _translate_content()

使用 LLM 翻译网页内容。

```python
async def _translate_content(self, event: AstrMessageEvent, content: str) -> str:
    """翻译网页内容"""
    # 调用 LLM 进行翻译
```

### _add_specific_content_to_result()

将特定提取的内容添加到分析结果中。

```python
def _add_specific_content_to_result(
    self, analysis_result: str, specific_content: dict
) -> str:
    """将特定内容添加到分析结果中"""
    # 格式化并添加图片、链接、视频等内容
```

### _batch_process_urls()

批量处理多个 URL。

```python
async def _batch_process_urls(
    self,
    event: AstrMessageEvent,
    urls: list,
    processing_message_id: int,
    bot: Any,
):
    """批量处理多个URL"""
    # 并发处理多个URL并返回结果
```

## 未来改进方案

### 方案 1：框架支持 Mixin 装饰器

建议 AstrBot 框架改进装饰器注册机制，支持扫描 Mixin 类中的装饰器：

```python
# 建议的框架改进
class Star:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 扫描所有 Mixin 类的装饰器
        for base in cls.__mro__:
            if hasattr(base, '__command_decorators__'):
                cls.__command_decorators__.extend(base.__command_decorators__)
```

### 方案 2：使用组合而非继承

改用组合模式：

```python
class WebAnalyzerPlugin(Star):
    
    def __init__(self, context, config):
        super().__init__(context)
        self.cmd_handler = WebCommandHandlers(self)
    
    def register_commands(self):
        """显式注册所有命令"""
        commands = {
            'web_help': self.cmd_handler.show_help,
            'web_config': self.cmd_handler.show_config,
            # ...
        }
        for cmd_name, handler in commands.items():
            self.context.register_command(cmd_name, handler)
```

### 方案 3：使用装饰器工厂

创建一个支持延迟注册的装饰器：

```python
def command_with_plugin(command_name, aliases=None):
    """创建一个可以绑定到插件实例的装饰器"""
    def decorator(method):
        method._command_name = command_name
        method._command_aliases = aliases or []
        return method
    return decorator

# 在命令处理器中使用
class WebCommandHandlers:
    
    @command_with_plugin("web_help", aliases=["网页分析帮助"])
    async def show_help(self, event):
        yield event.plain_result("...")

# 在主类中注册
class WebAnalyzerPlugin(Star):
    
    def __init__(self, context, config):
        super().__init__(context)
        self.cmd_handler = WebCommandHandlers(self)
        self._register_commands()
    
    def _register_commands(self):
        """注册所有命令"""
        for attr_name in dir(self.cmd_handler):
            attr = getattr(self.cmd_handler, attr_name)
            if hasattr(attr, '_command_name'):
                # 注册命令
                self._register_single_command(attr)
```

## 总结

`core/command_handlers.py` 模块虽然目前无法直接通过 Mixin 模式使用，但仍然具有以下价值：

1. **代码组织参考**：展示了如何将命令处理逻辑分离
2. **重构基础**：为未来的重构提供了清晰的实现方案
3. **文档作用**：详细记录了每个命令的处理逻辑
4. **维护便利**：修改命令逻辑时可以参考该模块

如果将来框架改进或找到解决方案，该模块可以立即投入使用，大幅简化 `main.py` 的代码结构。

## 相关文件

- `main.py` - 当前使用的命令处理实现
- `core/plugin_helpers.py` - 可用的辅助方法模块
- `core/message_handler.py` - 消息处理逻辑模块
- `docs/command_handlers_guide.md` - 本文档