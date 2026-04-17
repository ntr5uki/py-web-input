# py-network-input

一个基于 `Streamlit` 的局域网文字投送工具：网页端输入或局域网设备 `POST` 文字到本机后端，本机再把文字输入到**当前焦点位置**。

## 当前实现

- 页面：`streamlit_app.py`
- 局域网接口：内置 `POST /send`
- 输入后端：Wayland `wtype`
- 历史记录：仅内存保存，重启清空

## 运行前准备

1. 安装 Python 依赖：

```bash
uv sync
```

2. 在 Linux Wayland 环境安装 `wtype`：

```bash
sudo apt install wtype
```

如果你的发行版不使用 `apt`，请改用对应包管理器安装。

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

## 可选环境变量

- `NETWORK_INPUT_HOST`：HTTP 服务地址，默认 `0.0.0.0`
- `NETWORK_INPUT_PORT`：HTTP 服务端口，默认 `8765`
- `NETWORK_INPUT_ENABLE_API`：是否开启 HTTP API，默认 `false`
- `NETWORK_INPUT_MAX_HISTORY`：历史记录条数，默认 `20`
- `NETWORK_INPUT_API_TOKEN`：设置后启用 Bearer Token 鉴权
- `NETWORK_INPUT_BACKEND`：输入后端，默认 `wtype`

## 注意事项

- 只有当光标位于可编辑控件中时，文字才能正确输入。
- `wtype` 未安装时，接口仍可接收消息，但执行会失败，错误会在页面中显示。
- 多行文本会自动转成空格分隔的一行，避免模拟回车影响当前窗口。
- 当前版本主要面向 **Linux Wayland**。
