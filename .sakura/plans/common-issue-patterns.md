# 常见问题模式

## 配置相关问题

### 1. 类型安全问题
**模式**：配置值为字符串时参与算术运算
```python
# 问题代码
self.timeout = config.get("timeout", "30")  # 字符串
self.timeout * 1000  # 类型错误
```

**解决方案**：
```python
# 正确代码
self.timeout = int(config.get("timeout", 30))  # 转换为整数
self.timeout * 1000  # 安全运算
```

**审查要点**：
- 所有使用 `self.timeout` 进行算术运算的地方，须确保其为 `int/float` 类型
- 配置解析时转换或增加运行时防御

### 2. 边界值未处理
**模式**：配置边界值（0、负数、None、空字符串）未在代码或测试中明确处理

**常见场景**：
- `timeout=0`：可能导致立即超时
- `timeout=-1`：可能导致无限等待
- `None` 值：可能导致属性访问错误
- 空字符串：可能导致类型转换错误

**解决方案**：
```python
# 配置验证层
def validate_timeout(timeout):
    if timeout is None:
        return DEFAULT_TIMEOUT
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    return int(timeout)
```

### 3. 配置同步遗漏
**模式**：配置项变更未同步更新 `_conf_schema.json`

**后果**：配置验证失效，可能导致运行时错误

**解决方案**：
- 配置项变更必须同步更新 `_conf_schema.json`
- 建议在 CI 中增加配置同步检查

## 超时与重试问题

### 1. 硬编码超时反模式
**模式**：浏览器操作中使用硬编码超时值
```python
# 问题代码
page.goto(url, timeout=30000)  # 硬编码 30 秒
```

**解决方案**：
```python
# 正确代码
page.goto(url, timeout=self.timeout * 1000)  # 使用配置超时
```

**审查要点**：
- 所有 `page.goto`/`page.screenshot` 等浏览器操作的超时必须统一使用实例超时配置
- 禁止任何硬编码超时值

### 2. 双客户端超时语义不一致
**模式**：playwright 使用毫秒，httpx 使用秒，单位转换错误

**常见错误**：
```python
# 错误：忘记转换单位
httpx_client.get(url, timeout=self.timeout)  # 应该是秒
playwright_page.goto(url, timeout=self.timeout)  # 应该是毫秒
```

**解决方案**：
```python
# 正确：明确单位转换
httpx_timeout = self.timeout  # 秒
playwright_timeout = self.timeout * 1000  # 毫秒
```

### 3. 策略降级可观测性不足
**模式**：策略降级时未记录日志或日志信息不完整

**问题代码**：
```python
# 问题：无日志记录
if networkidle_timeout:
    page.goto(url, timeout=networkidle_timeout)
else:
    page.goto(url, timeout=fixed_timeout)  # 降级但无日志
```

**解决方案**：
```python
# 正确：记录降级日志
if networkidle_timeout:
    page.goto(url, timeout=networkidle_timeout)
else:
    logger.info(f"策略降级: networkidle → fixed, 原因: 超时 {networkidle_timeout}ms")
    page.goto(url, timeout=fixed_timeout)
```

## 版本管理问题

### 1. 分离式版本号提交
**模式**：核心修复与版本递增拆分为独立 PR 或提交

**风险**：增量审查中容易遗漏版本一致性检查

**解决方案**：
- 审查版本递增提交时，强制检查历史修复上下文
- 确认所有版本定义文件已同步更新

### 2. 版本号同步遗漏
**模式**：双版本号文件（`main.py` + `metadata.yaml`）不同步

**后果**：插件版本信息不一致，可能导致功能异常

**解决方案**：
- 版本号变更时检查所有定义版本号的文件
- 建议在 CI 中增加版本号同步校验脚本

### 3. 依赖版本提升风险
**模式**：硬性拉高最低版本可能阻断旧宿主环境用户

**常见场景**：
- httpx 从 0.24 升级到 0.28，API 发生破坏性变更
- 最低版本提升未注明依赖的特定 API/Feature

**解决方案**：
- 依赖最低版本提升必须注明依赖的特定 API/Feature
- 评估生态风险，考虑向后兼容性

## 系统解析问题

### 1. 脆弱字符串匹配
**模式**：解析系统命令输出时依赖固定数量空白符匹配

**问题代码**：
```python
# 问题：依赖固定空白符数量
output = subprocess.check_output("id", shell=True).decode()
uid = output.split()[1]  # 假设第二个字段是 UID
```

**解决方案**：
```python
# 正确：按语义提取
output = subprocess.check_output("id", shell=True).decode()
# 使用正则或按语义解析
import re
uid_match = re.search(r'uid=(\d+)', output)
if uid_match:
    uid = uid_match.group(1)
```

### 2. 容器环境假阳性
**模式**：白名单模式可避免误判（如含有 docker 字样的自定义环境变量）

**常见误判**：
- 环境变量包含 "docker" 字样但实际不是 Docker 环境
- `/proc` 解析错误导致误判

**解决方案**：
- 引入白名单机制收敛枚举边界
- 逆向思考“什么情况下会被误判为 Docker”

## 审查流程问题

### 1. 修复遮蔽效应
**模式**：当上一轮遗留问题集中在特定文件时，审查员视线容易被锚定

**后果**：忽略同一文件中其他函数的实际调用变更

**解决方案**：
- 审查时主动检查文件中所有函数的调用变更
- 避免只关注特定代码块的修改

### 2. 增量审查盲区
**模式**：仅看 diff 无法评估新功能在入口文件中的调度逻辑

**后果**：遗漏功能闭环检查

**解决方案**：
- 无历史记忆的增量审查若涉及新功能，须阅读核心入口文件
- 强制检查历史上下文

### 3. 评分通货膨胀
**模式**：连续出现 9/10、10/10 但实际变更微小

**后果**：削弱审查信任度

**解决方案**：
- 严格执行评分校准规则
- 纯版本号/注释/格式化变更评分 ≤ 8/10

## 架构设计问题

### 1. 单文件职责过重
**模式**：`analyzer.py` 承载 HTTP 请求、截图、策略选择等多职责

**风险**：变更时牵一发动全身，耦合度高

**改进方向**：
- 考虑职责分离，将不同功能模块化
- HTTP 客户端、浏览器自动化、策略选择等功能独立成模块

### 2. 错误信息丢失
**模式**：异常包装无上下文，损害可观测性

**问题代码**：
```python
# 问题：无上下文的笼统错误
try:
    page.goto(url)
except Exception as e:
    raise Exception("截图生成失败")  # 丢失原始异常信息
```

**解决方案**：
```python
# 正确：传递原始异常信息
try:
    page.goto(url)
except Exception as e:
    raise Exception(f"截图生成失败: {str(e)}") from e
```

## 测试覆盖问题

### 1. 超时逻辑测试缺失
**模式**：涉及超时、重试、降级逻辑的 PR 缺少测试覆盖

**风险**：边界情况未验证，可能导致运行时错误

**解决方案**：
- 要求涉及超时、重试、降级逻辑的 PR 必须附带测试
- 测试应覆盖边界值（0、负数、超大值）

### 2. 配置边界测试缺失
**模式**：配置边界值未在测试中明确处理

**常见遗漏**：
- `timeout=0` 的行为
- `timeout=-1` 的处理
- `None` 值的默认值应用

**解决方案**：
- 配置边界值必须在代码或测试中明确处理
- 建立配置验证测试套件