# 生命周期管理模式

## 功能对称性审查

### 核心原则
当插件提供"安装/初始化"功能时，应主动检查是否存在对应的"卸载/清理"能力。缺失即形成 Issue 候选。

### 审查要点
1. **功能对称性检查清单**：
   - 安装功能 → 卸载功能
   - 初始化配置 → 重置/清理配置
   - 启动服务 → 停止服务
   - 启用插件 → 禁用插件

2. **常见缺失场景**：
   - 浏览器安装后无卸载指令
   - 配置文件生成后无清理机制
   - 缓存数据创建后无清理功能
   - 临时文件创建后无自动删除

## 删除操作的前置条件

### 风险识别
涉及删除关键目录（如 `.playwright`）时，务必在分析中列出：

1. **进程占用检查**：
   - 检查浏览器是否正在被其他进程使用
   - 检查是否有截图任务正在进行
   - 检查 `_is_installing` 标志状态

2. **权限降级处理**：
   - 处理 `shutil.rmtree` 的权限问题
   - 处理文件被锁定的情况
   - 提供管理员权限提升提示

3. **失败回滚机制**：
   - 删除失败时不应导致插件崩溃
   - 保留原有浏览器目录
   - 提供手动删除指引

### 实现建议
```python
# 异步状态同步示例
async def uninstall_browser():
    async with asyncio.Lock():  # 使用锁保护
        if _is_installing:
            raise Exception("安装进行中，无法卸载")
        if browser_pool.is_busy():
            raise Exception("截图任务进行中，无法卸载")
        
        try:
            shutil.rmtree(browser_path)
        except PermissionError:
            logger.error("权限不足，无法删除浏览器目录")
            raise Exception("权限不足，请手动删除或以管理员权限运行")
        except Exception as e:
            logger.error(f"卸载失败: {e}")
            # 保留目录，提供手动删除指引
            raise Exception(f"卸载失败: {e}\n请手动删除目录: {browser_path}")
```

## 异步状态同步

### 竞态条件风险
`_is_installing` 与浏览器池忙碌状态的复合检查是易错点。

### 解决方案
1. **使用锁保护**：
   ```python
   import asyncio
   
   _install_lock = asyncio.Lock()
   
   async def install_browser():
       async with _install_lock:
           if _is_installing:
               return
           _is_installing = True
           try:
               # 安装逻辑
               pass
           finally:
               _is_installing = False
   ```

2. **状态持久化**：
   - 将安装状态保存到配置文件
   - 插件重启后能恢复状态
   - 避免状态丢失导致的竞态条件

## 仓库特有模式建议

### Lifecycle 标签
建立 `lifecycle` 标签，专门标记安装/卸载/重置类 Issue。

### 帮助信息同步
支持性功能（卸载）应要求作者同时更新：
1. `show_help` 命令的帮助信息
2. `metadata.yaml` 中的能力描述
3. README 文档

## 分析流程优化

### 极简标题处理
对于"新功能"这类极简标题，**必须**主动要求分析者从代码库中推断真实意图。

### 风险缓解建议
在可行性分析中增加"风险缓解建议"小节：
- 卸载失败时不应导致插件崩溃
- 应保留原有浏览器目录
- 提供手动删除指引

## 经验教训总结

### 值得未来关注的要点
1. **功能对称性审查**：当插件提供"安装/初始化"功能时，应主动检查是否存在对应的"卸载/清理"能力
2. **删除操作的前置条件**：涉及删除关键目录时，务必检查进程占用、权限、回滚机制
3. **异步状态同步**：使用锁保护复合状态检查，避免竞态条件

### 仓库特有模式
- 建立 `lifecycle` 标签专门标记安装/卸载/重置类 Issue
- 支持性功能应要求更新帮助信息和元数据描述
- 对极简标题必须主动推断真实意图