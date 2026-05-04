# AstrBot 配置文件

> 来源: https://docs.astrbot.app/dev/astrbot-config.html

---

## data/cmd_config.json

AstrBot 的配置文件是一个 JSON 格式的文件。AstrBot 会在启动时读取这个文件，并根据文件中的配置来初始化 AstrBot，其路径位于 `data/cmd_config.json`。

在 AstrBot v4.0.0 版本及之后，我们引入了多配置文件的概念。`data/cmd_config.json` 作为默认配置文件 `default`。其他您在 WebUI 新建的配置文件会存储在 `data/config/` 目录下，以 `abconf_` 开头。

### 主要配置项

#### `provider` (已废弃)

此配置项已经在 v4.0.0 版本之后被废弃。请使用 WebUI 来配置 LLM 提供商。

已配置的 LLM 提供商列表。每个提供商包含 `id`, `type`, `enable` 等字段。

#### `persona` (已废弃)

此配置项已经在 v4.0.0 版本之后被废弃。请使用 WebUI 来配置人格。

已配置的人格列表。每个人格包含 `id`, `name`, `description`, `system_prompt` 四个字段。

#### `timezone`

时区设置。请填写 IANA 时区名称，如 `Asia/Shanghai`，为空时使用系统默认时区。

所有时区请查看: [IANA Time Zone Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)。

#### `callback_api_base`

AstrBot API 的基础地址。用于文件服务和插件回调等功能。如 `http://localhost:6185`。

#### `default_kb_collection`

默认知识库名称。用于 RAG 功能。如果为空，则不使用知识库。

#### `plugin_set`

已启用的插件列表。`["*"]` 表示启用所有可用的插件。默认为 `["*"]`。

```json
{
    "plugin_set": ["*"]
}
```

#### `pip_install`

pip 安装参数。可以指定镜像源等。

```json
{
    "pip_install": "-i https://pypi.tuna.tsinghua.edu.cn/simple"
}
```

#### `pypi_index_url`

PyPI 镜像源地址。默认为 `https://pypi.org/simple`。
