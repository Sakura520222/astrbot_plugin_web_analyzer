# 开发指南

## 环境

- Python 3.10+（跟随宿主 AstrBot 的 Python 版本）
- 依赖：插件运行依赖见 `requirements.txt`（仅 `beautifulsoup4`、`lxml`）；`httpx`、`websockets`、`psutil`、`Pillow` 由宿主提供
- Ruff 用于格式化与检查

```bash
# 在 AstrBot 根目录的虚拟环境中执行
ruff format core/ main.py tests/
ruff check .
```

## 运行测试

```bash
cd tests
python -m unittest discover -s . -p "test_*.py"   # 127 项，无需 AstrBot 实例
node --test dashboard.test.mjs                    # 7 项前端测试

# 本机浏览器集成测试（需要已安装 Chrome/Edge/Chromium）
WEB_ANALYZER_BROWSER_TESTS=1 python -m unittest test_browser_runtime
```

`tests/test_support.py` 桩替 `astrbot.api` 并直载核心模块，测试数据写入 `tests/.scratch/`，不会触碰宿主数据目录。

## 调试

在 AstrBot 开发实例的 `data/plugins/` 下符号链接本仓库，重载插件后观察日志：

```bash
mklink /D AstrBot\data\plugins\astrbot_plugin_web_analyzer <仓库路径>   # Windows
ln -s <仓库路径> AstrBot/data/plugins/astrbot_plugin_web_analyzer       # Linux/macOS
```

修改 `_conf_schema.json`、`metadata.yaml` 或 i18n 资源后需重载插件生效。

## 代码约定

- 配置键为英文小写下划线；配置描述、日志与文档面向用户的部分使用中文
- 新增 docstring 使用 Google 格式
- 优先使用 `astrbot.api` 公开接口；`astrbot.core` 内部接口需按目标版本核对
- 插件版本三处同步：`metadata.yaml`、`main.py` 的 `@register`、`views/dashboard/index.html` 的版本脚注

## 版本发布

1. 更新 `CHANGELOG.md`（`### [vX.Y.Z] - 日期`）；
2. 同步三处版本号；
3. 提交并推送 `main`，CI（`.github/workflows/release.yml`）按 `metadata.yaml` 的版本自动打标签并发布 Release。

## 提交规范

使用 Conventional Commits：`feat:`、`fix:`、`docs:`、`refactor:`、`test:`、`chore:`。提交前运行 `ruff format` 与全部测试。
