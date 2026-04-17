from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import PurePosixPath
import threading
from typing import Any

from .config import AppConfig
from .models import MessageRecord
from .service import MessageService


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def create_handler(service: MessageService, config: AppConfig) -> type[BaseHTTPRequestHandler]:
    class ApiHandler(BaseHTTPRequestHandler):
        server_version = "LanInput/0.1"

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_common_headers()
            self.end_headers()

        def do_GET(self) -> None:
            path = PurePosixPath(self.path.split("?", 1)[0])
            if path == PurePosixPath("/"):
                self._send_html(HTTPStatus.OK, render_index_html(config))
                return
            if path == PurePosixPath("/health"):
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "backend_ready": service.backend_ready(),
                        "pending": service.pending_count(),
                    },
                )
                return
            if path == PurePosixPath("/api/history"):
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "items": [item.to_dict() for item in service.list_history()],
                        "pending": service.pending_count(),
                        "backend_ready": service.backend_ready(),
                    },
                )
                return
            if path == PurePosixPath("/api/status"):
                latest = service.list_history()[0] if service.list_history() else None
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "backend_ready": service.backend_ready(),
                        "pending": service.pending_count(),
                        "latest": latest.to_dict() if latest else None,
                    },
                )
                return
            self._send_error(HTTPStatus.NOT_FOUND, "未找到接口。")

        def do_POST(self) -> None:
            path = PurePosixPath(self.path.split("?", 1)[0])
            if path == PurePosixPath("/send"):
                if not self._authorized():
                    self._send_error(HTTPStatus.UNAUTHORIZED, "鉴权失败。")
                    return
                payload = self._read_json_payload()
                if payload is None:
                    return
                record = self._submit_legacy_send(payload)
                if record is None:
                    return
                self._send_record(record)
                return

            if path == PurePosixPath("/api/send"):
                payload = self._read_json_payload()
                if payload is None:
                    return
                record = self._submit_ui_send(payload)
                if record is None:
                    return
                self._send_record(record)
                return

            if path == PurePosixPath("/api/enter"):
                record = service.submit_enter(source="web")
                self._send_record(record)
                return

            self._send_error(HTTPStatus.NOT_FOUND, "未找到接口。")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json_payload(self) -> dict[str, Any] | None:
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            if content_length <= 0 or content_length > 64_000:
                self._send_error(HTTPStatus.BAD_REQUEST, "请求体大小不合法。")
                return None

            try:
                payload = json.loads(self.rfile.read(content_length))
            except json.JSONDecodeError:
                self._send_error(HTTPStatus.BAD_REQUEST, "请求体不是合法 JSON。")
                return None
            if not isinstance(payload, dict):
                self._send_error(HTTPStatus.BAD_REQUEST, "请求体必须是 JSON 对象。")
                return None
            return payload

        def _submit_legacy_send(self, payload: dict[str, Any]) -> MessageRecord | None:
            text = payload.get("text")
            source = payload.get("source", "api")
            if not isinstance(text, str):
                self._send_error(HTTPStatus.BAD_REQUEST, "`text` 必须是字符串。")
                return None
            if not isinstance(source, str):
                source = "api"

            try:
                return service.submit(text=text, source=source)
            except ValueError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "未找到接口。")
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return None

        def _submit_ui_send(self, payload: dict[str, Any]) -> MessageRecord | None:
            text = payload.get("text")
            source = payload.get("source", "web")
            auto_paste = bool(payload.get("auto_paste", False))
            shortcut = payload.get("shortcut", "ctrl+v")
            if not isinstance(text, str):
                self._send_error(HTTPStatus.BAD_REQUEST, "`text` 必须是字符串。")
                return None
            if not isinstance(source, str):
                source = "web"
            if not isinstance(shortcut, str):
                shortcut = "ctrl+v"
            try:
                if auto_paste:
                    return service.submit_with_auto_paste(text=text, source=source, shortcut=shortcut)
                return service.submit(text=text, source=source)
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return None

        def _send_record(self, record: MessageRecord) -> None:
            self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "record": record.to_dict()})

        def _authorized(self) -> bool:
            if not config.api_token:
                return True
            header = self.headers.get("Authorization", "")
            return header == f"Bearer {config.api_token}"

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json(status, {"ok": False, "error": message})

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: HTTPStatus, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_common_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    return ApiHandler


class ApiServer:
    def __init__(self, service: MessageService, config: AppConfig) -> None:
        handler = create_handler(service, config)
        self._server = ThreadingHTTPServer((config.host, config.port), handler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="network-input-http-api",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)


def render_index_html(config: AppConfig) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>局域网文字投送</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      margin: 0;
      background: #0f172a;
      color: #e2e8f0;
    }}
    .wrap {{
      max-width: 920px;
      margin: 0 auto;
      padding: 20px;
    }}
    .card {{
      background: #111827;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    textarea {{
      width: 100%;
      min-height: 150px;
      border-radius: 12px;
      border: 1px solid #475569;
      background: #020617;
      color: #e2e8f0;
      padding: 12px;
      font-size: 16px;
      box-sizing: border-box;
    }}
    .row {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 12px;
    }}
    button {{
      border: 0;
      border-radius: 12px;
      padding: 12px 16px;
      cursor: pointer;
      font-size: 15px;
      background: #2563eb;
      color: white;
    }}
    button.secondary {{
      background: #475569;
    }}
    .status {{
      font-weight: 600;
      margin-bottom: 10px;
    }}
    .success {{ color: #22c55e; }}
    .error {{ color: #ef4444; }}
    .muted {{ color: #94a3b8; }}
    .history-item {{
      padding: 10px 0;
      border-top: 1px solid #334155;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    label {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>局域网文字投送</h1>
      <p class="muted">手机浏览器可直接访问。默认写入剪贴板；可选自动上屏或单独发送回车。</p>
      <div id="banner" class="status muted">等待发送</div>
    </div>

    <div class="card">
      <textarea id="text" placeholder="输入要投送的文字"></textarea>
      <div class="row">
        <label><input id="autoPaste" type="checkbox"> 自动上屏</label>
        <label><input type="radio" name="shortcut" value="ctrl+v" checked> Ctrl+V</label>
        <label><input type="radio" name="shortcut" value="ctrl+shift+v"> Ctrl+Shift+V</label>
      </div>
      <div class="row">
        <button id="sendButton">发送文本</button>
        <button id="enterButton" class="secondary">发送回车</button>
      </div>
    </div>

    <div class="card">
      <div id="meta" class="muted">后端类型：{config.input_backend} · 通知：{"开启" if config.enable_notifications else "关闭"}</div>
      <div id="history"></div>
    </div>
  </div>

  <script>
    const textEl = document.getElementById("text");
    const autoPasteEl = document.getElementById("autoPaste");
    const sendButton = document.getElementById("sendButton");
    const enterButton = document.getElementById("enterButton");
    const banner = document.getElementById("banner");
    const historyEl = document.getElementById("history");

    function selectedShortcut() {{
      return document.querySelector('input[name="shortcut"]:checked').value;
    }}

    function setBanner(message, kind="muted") {{
      banner.className = `status ${{kind}}`;
      banner.textContent = message;
    }}

    async function sendJson(url, payload) {{
      const response = await fetch(url, {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json"
        }},
        body: JSON.stringify(payload)
      }});
      return await response.json();
    }}

    function actionLabel(item) {{
      if (item.action === "copy_and_paste") return `复制并自动上屏（${{item.shortcut}}）`;
      if (item.action === "press_key") return "发送回车";
      return "复制到剪贴板";
    }}

    async function refreshHistory() {{
      const response = await fetch("/api/history");
      const payload = await response.json();
      if (!payload.ok) return;
      historyEl.innerHTML = "";
      if (!payload.items.length) {{
        historyEl.innerHTML = '<div class="muted">暂无记录</div>';
        return;
      }}
      for (const item of payload.items) {{
        const div = document.createElement("div");
        div.className = "history-item";
        div.textContent = `${{item.message_id}} · ${{item.status}} · ${{actionLabel(item)}}\\n${{item.action === "press_key" ? "（无文本内容）" : item.text}}`;
        historyEl.appendChild(div);
      }}
    }}

    sendButton.addEventListener("click", async () => {{
      const payload = {{
        text: textEl.value,
        source: "web",
        auto_paste: autoPasteEl.checked,
        shortcut: selectedShortcut()
      }};
      const result = await sendJson("/api/send", payload);
      if (result.ok) {{
        textEl.value = "";
        if (result.record.action === "copy_and_paste") {{
          setBanner(`已发送并尝试自动上屏：${{result.record.shortcut}}`, "success");
        }} else {{
          setBanner("已复制到剪贴板，请手动粘贴。", "success");
        }}
        refreshHistory();
      }} else {{
        setBanner(result.error || "发送失败", "error");
      }}
    }});

    enterButton.addEventListener("click", async () => {{
      const result = await sendJson("/api/enter", {{}});
      if (result.ok) {{
        setBanner("已发送回车。", "success");
        refreshHistory();
      }} else {{
        setBanner(result.error || "发送回车失败", "error");
      }}
    }});

    refreshHistory();
    setInterval(refreshHistory, 2000);
  </script>
</body>
</html>"""
