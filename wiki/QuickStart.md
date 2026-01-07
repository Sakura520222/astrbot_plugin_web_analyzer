# 快速开始

## 安装插件

### 1. 下载插件

从GitHub Releases页面下载最新版本的插件压缩包，或者直接克隆代码库：

```bash
git clone https://github.com/Sakura520222/astrbot_plugin_web_analyzer.git
```

### 2. 复制到插件目录

将插件目录复制到AstrBot的插件目录中：

```bash
# 目录结构示例
AstrBot/data/plugins/
└── astrbot_plugin_web_analyzer/
    ├── main.py
    ├── requirements.txt
    └── ...
```

### 3. 安装依赖

进入插件目录，安装所需的依赖：

```bash
# 进入插件目录
cd AstrBot/data/plugins/astrbot_plugin_web_analyzer
# 安装依赖
pip install -r requirements.txt
```

### 4. 重载插件

重启AstrBot或在WebUI插件管理中点击**重载插件**按钮，使插件生效。

## 基本使用

### 自动分析

插件会自动检测消息中的URL链接并进行分析。当用户发送包含URL的消息时，插件会自动识别并处理：

```
用户：看看这个新闻 https://example.com/news/article
机器人：检测到网页链接，正在分析: https://example.com/news/article
       [分析结果...]
       [网页截图...]
```

### 支持无协议头URL

在配置中启用`enable_no_protocol_url`选项后，插件可以识别无协议头的URL：

```
用户：看看这个新闻 www.example.com/news/article
机器人：检测到网页链接，正在分析: https://www.example.com/news/article
       [分析结果...]
       [网页截图...]
```

### 多链接处理

插件支持同时处理多个链接，会合并成一条合并转发消息发送：

```
用户：看看这些新闻 https://example.com/news/article1 https://example.com/news/article2
机器人：检测到2个网页链接，正在分析...
       [合并转发的分析结果...]
       [网页截图...]
```

### 手动分析

使用命令手动分析指定链接：

```
/网页分析 https://example.com
```

### 查看帮助

查看所有可用命令和帮助信息：

```
/web_help
```

## 下一步

- 查看[命令参考](Commands.md)了解所有可用命令
- 查看[配置指南](Configuration.md)了解如何配置插件
- 查看[常见问题](FAQ.md)解决可能遇到的问题