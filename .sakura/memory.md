# Memory - astrbot_plugin_web_analyzer

## 常见代码问题和审查要点

- **httpx API 变更敏感区**：`proxies`(dict) → `proxy`(str) 是渐进式废弃陷阱，审查 HTTP 客户端代码时须关注 Auth、Proxy、SSL 参数的版本兼容性
- **策略模式降级路径**：`fixed/networkidle/smart` 截图策略需重点审查降级链的边界条件（如 `networkidle` 在 SPA 页面可能永不触发）和可观测性（降级日志）
- **日志级别业务含义**：异步耗时操作（如截图）的日志级别变更直接影响宿主 AstrBot 控制台排障体验，需确认是否符合生命周期（调试 vs 默认展示）
- **单文件职责过重**：`analyzer.py` 承载 HTTP 请求、截图、策略选择等多职责，变更时需警惕牵一发动全身

## 近期审查模式总结

- **小步迭代提交**：Bug 修复和新功能常拆分为多次提交，最后用单独提交修正版本约束和日志细节，增量审查易丢失全局视角
- **配置驱动架构**：行为完全由配置决定（`_conf_schema.json`），配置层→入口层→消息处理层→核心分析层
- **增量审查盲区**：仅看 diff 无法评估新功能在 `message_handler.py` 等入口文件中的调度逻辑是否正确

## 规范建议

| 规则 | 说明 |
|------|------|
| `dep-version-context` | 依赖最低版本提升必须注明依赖的特定 API/Feature |
| `dep-compat-guard` | `quick` 策略下若涉及包管理文件变更，仍须检查依赖兼容性 |
| `schema-sync` | 配置项变更必须同步 `_conf_schema.json` |
| `strategy-logging` | 策略降级必须记录日志（含原因和降级目标） |
| `backwards-compat` | 新增配置项必须考虑旧配置文件的兼容处理 |
| `pr-desc-diff-match` | PR 描述提到的文件必须出现在 diff 中，否则追问 |
| `incremental-context` | 无历史记忆的增量审查若涉及新功能，须阅读核心入口文件 |

## 经验教训

- **高评分陷阱**：9/10 应对应近乎完美，功能完整但验证不足时应降至 7/10，避免"点赞式审查"
- **决策必须明确**：禁止使用 `unknown`，强制选择 `approve` 或 `request_changes`
- **隐式版本风险**：硬性拉高最低版本可能阻断旧宿主环境用户，微小 diff（如 +2/-2）中可能隐藏生态风险
- **截图超时避免硬编码**：统一使用可配置阈值；代理配置变更需验证 `None`/空字符串边界