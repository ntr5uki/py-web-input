# py-network-input

一个轻量的局域网文字投送工具：内置 HTTP 服务同时提供手机网页端和接口，本机收到文字后写入 Wayland 剪贴板；网页端还可选自动上屏，或单独发送一个回车按键。

## 当前实现

- 页面：内置 HTML 手机网页
- 局域网接口：内置网页接口和脚本接口 `POST /send`
- 输入后端：Wayland `wl-copy`
- 网页增强：可选 `Ctrl+V` / `Ctrl+Shift+V` 自动上屏、单独发送回车
- 历史记录：仅内存保存，重启清空

## 运行前准备

1. 安装 Python 依赖：

```bash
uv sync
```

2. 在 Linux Wayland 环境安装 `wl-clipboard`：

```bash
sudo apt install wl-clipboard
```

如果你的发行版不使用 `apt`，请改用对应包管理器安装。

如果要使用网页里的“自动上屏”或“发送回车”，还需要安装：

```bash
sudo apt install wtype
```

## 启动

```bash
uv run python -m network_input
```

也可以直接从 GitHub 运行：

```bash
uvx --from git+https://github.com/ntr5uki/py-web-input py-web-input
```

默认服务监听：

- `0.0.0.0:18502`

启动后不会自动打开浏览器，手动访问：

- `http://localhost:18502`
- `http://你的局域网IP:18502`

页面和接口都复用同一个端口，不再额外占用 `8765`。

启动后如果当前终端可交互，会额外开启配对命令行：

- `list`：查看待确认联机请求
- `allow <id>`：允许某个请求
- `deny <id>`：拒绝某个请求

## 接口

### 网页联机流程

- 手机首次打开页面时，只能先点击“申请联机”
- 主控端在当前服务终端执行 `allow <id>` 或 `deny <id>`
- 允许后，该网页设备获得当天有效的联机会话
- 会话只保存在内存中，重启服务后需要重新联机

### `POST /send`

说明：

- 该接口保留给脚本调用
- 必须配置 `NETWORK_INPUT_API_TOKEN`
- 必须携带 `Authorization: Bearer <API_TOKEN>`

请求体：

```json
{
  "text": "你好，世界",
  "source": "phone"
}
```

示例：

```bash
curl -X POST \
  -H 'Authorization: Bearer secret-token' \
  -H 'Content-Type: application/json' \
  -d '{"text":"你好，来自局域网设备","source":"curl"}' \
  http://127.0.0.1:18502/send
```

## 网页操作

- `发送文本`：把内容写入剪贴板
- `自动上屏`：勾选后在写入剪贴板后再发送粘贴快捷键
- `粘贴快捷键`：
  - `Ctrl+V`：适合普通 GUI 输入框
  - `Ctrl+Shift+V`：适合 `kitty` 等终端
- `发送回车`：单独发送一个回车按键，不依赖文本内容
- `断开联机`：清除当前网页的本地会话

## 可选环境变量

- `NETWORK_INPUT_HOST`：HTTP 服务地址，默认 `0.0.0.0`
- `NETWORK_INPUT_PORT`：HTTP 服务端口，默认 `18502`
- `NETWORK_INPUT_ENABLE_NOTIFICATIONS`：是否开启系统通知，默认 `false`
- `NETWORK_INPUT_MAX_HISTORY`：历史记录条数，默认 `20`
- `NETWORK_INPUT_API_TOKEN`：脚本接口 `/send` 的 Bearer Token
- `NETWORK_INPUT_BACKEND`：输入后端，默认 `clipboard`

## 注意事项

- 发送后只会写入剪贴板，不会自动模拟键盘或粘贴。
- 系统通知默认关闭；如需开启，启动前设置 `NETWORK_INPUT_ENABLE_NOTIFICATIONS=true`。
- `wl-copy` 未安装时，接口仍可接收消息，但执行会失败，错误会在页面中显示。
- 勾选自动上屏或点击发送回车时，需要本机安装 `wtype`。
- 多行文本会保留换行，最终粘贴效果取决于目标应用。
- 网页接口默认需要先联机；脚本接口 `/send` 则始终依赖 `API_TOKEN`。
- 当前版本主要面向 **Linux Wayland**。
