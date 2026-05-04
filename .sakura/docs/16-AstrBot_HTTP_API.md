# AstrBot HTTP API

> 来源: https://docs.astrbot.app/dev/openapi.html

---

从 v4.18.0 开始，AstrBot 提供基于 API Key 的 HTTP API，开发者可以通过标准 HTTP 请求访问核心能力。

## 快速开始

HTTP API 使用 API Key 进行认证，在请求头中携带：

```
Authorization: Bearer abk_xxx
```

也支持：

```
X-API-Key: abk_xxx
```

> **NOTE**: `POST /api/v1/chat` 需要传入 `username` 参数。`GET /api/v1/chat/sessions` 也需要 `username`。

## Scope 权限说明

创建 API Key 时可配置 `scopes`。每个 scope 控制可访问的接口范围：

| Scope | 说明 |
|-------|------|
| `chat` | 聊天相关接口 |
| `im` | 即时消息接口 |
| `file` | 文件上传接口 |
| `admin` | 管理接口 |

## 消息段类型

API 中支持的消息段 `type`：

| type | 必填字段 | 可选字段 | 说明 |
|------|---------|---------|------|
| `plain` | `text` | | 文本段 |
| `reply` | `message_id` | `selected_text` | 引用回复某条消息 |
| `image` | `attachment_id` | | 图片附件段 |
| `record` | `attachment_id` | | 音频附件段 |
| `file` | `attachment_id` | | 通用文件段 |
| `video` | `attachment_id` | | 视频附件段 |

> **说明**: `attachment_id` 需先通过 `POST /api/v1/file` 上传文件获取。`reply` 段可以和其他段（`plain/image/file/...`）组合使用。

## Chat API

### POST /api/v1/chat

发送消息进行对话。

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | ✅ | 用户名 |
| `message` | string/array | ✅ | 消息内容 |
| `session_id` | string | ❌ | 会话ID（不传会自动创建 UUID） |

### Chat API 的 `message` 用法

`message` 字段支持字符串和数组两种格式：

**字符串格式：**

```json
{
    "username": "test_user",
    "message": "你好"
}
```

**数组格式（富媒体消息）：**

```json
{
    "username": "test_user",
    "message": [
        {"type": "plain", "text": "看这张图"},
        {"type": "image", "attachment_id": "xxx"}
    ]
}
```

## IM 消息发送

### POST /api/v1/im/message

通过 IM 平台直接发送消息。

## 文件上传

### POST /api/v1/file

上传文件，返回 `attachment_id` 用于消息发送。

## 会话管理

### GET /api/v1/chat/sessions

获取用户的会话列表（需要 `username` 参数）。

## 完整 API 文档

详细的 API 文档和交互式测试界面可通过 AstrBot 的 Scalar 页面访问：

- 地址：`http://your-astrbot-host:6185/scalar.html`
- 或参考：https://docs.astrbot.app/scalar.html
