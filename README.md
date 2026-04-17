# py-network-input

一个基于 `Streamlit` 的局域网文字投送工具：网页端输入或局域网设备 `POST` 文字到本机后端，本机先写入 Wayland 剪贴板；网页端还可选自动上屏，或单独发送一个回车按键。

## 当前实现

- 页面：`streamlit_app.py`
- 局域网接口：内置 `POST /send`
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
uv run streamlit run streamlit_app.py
```

默认 Streamlit 页面监听：

- `0.0.0.0:18502`

启动后不会自动打开浏览器，手动访问：

- `http://localhost:18502`

默认不会启动额外的 HTTP API，因此不会监听 `8765`。如果需要让局域网设备直接调用接口，可以开启 HTTP API：

```bash
NETWORK_INPUT_ENABLE_API=true uv run streamlit run streamlit_app.py
```

开启后会在 Streamlit 进程里同时启动一个 HTTP 服务，监听：

- `0.0.0.0:8765`
- 页面里会展示可直接调用的本机地址

## 接口

### `POST /send`

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
  -H 'Content-Type: application/json' \
  -d '{"text":"你好，来自局域网设备","source":"curl"}' \
  http://127.0.0.1:8765/send
```

## 网页操作

- `发送文本`：把内容写入剪贴板
- `自动上屏`：勾选后在写入剪贴板后再发送粘贴快捷键
- `粘贴快捷键`：
  - `Ctrl+V`：适合普通 GUI 输入框
  - `Ctrl+Shift+V`：适合 `kitty` 等终端
- `发送回车`：单独发送一个回车按键，不依赖文本内容

## 可选环境变量

- `NETWORK_INPUT_HOST`：HTTP 服务地址，默认 `0.0.0.0`
- `NETWORK_INPUT_PORT`：HTTP 服务端口，默认 `8765`
- `NETWORK_INPUT_ENABLE_API`：是否开启 HTTP API，默认 `false`
- `NETWORK_INPUT_ENABLE_NOTIFICATIONS`：是否开启系统通知，默认 `false`
- `NETWORK_INPUT_MAX_HISTORY`：历史记录条数，默认 `20`
- `NETWORK_INPUT_API_TOKEN`：设置后启用 Bearer Token 鉴权
- `NETWORK_INPUT_BACKEND`：输入后端，默认 `clipboard`

## 注意事项

- 发送后只会写入剪贴板，不会自动模拟键盘或粘贴。
- 系统通知默认关闭；如需开启，启动前设置 `NETWORK_INPUT_ENABLE_NOTIFICATIONS=true`。
- `wl-copy` 未安装时，接口仍可接收消息，但执行会失败，错误会在页面中显示。
- 勾选自动上屏或点击发送回车时，需要本机安装 `wtype`。
- 多行文本会保留换行，最终粘贴效果取决于目标应用。
- 当前版本主要面向 **Linux Wayland**。
