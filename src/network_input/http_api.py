from __future__ import annotations

from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import PurePosixPath
import threading
from typing import Any

from .auth import PairingManager
from .config import AppConfig
from .models import MessageRecord
from .service import MessageService


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def create_handler(
    service: MessageService,
    config: AppConfig,
    pairing: PairingManager,
) -> type[BaseHTTPRequestHandler]:
    class ApiHandler(BaseHTTPRequestHandler):
        server_version = "LanInput/0.2"

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
                        "pair_pending": len(pairing.list_pending_requests()),
                    },
                )
                return
            if path == PurePosixPath("/api/pair/status"):
                client_id = self._require_client_id()
                if client_id is None:
                    return
                payload = pairing.get_pair_status(client_id, self._session_token())
                self._send_json(HTTPStatus.OK, {"ok": True, **payload})
                return

            client_id = self._require_authorized_session()
            if client_id is None:
                return

            if path == PurePosixPath("/api/history"):
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "items": [item.to_dict() for item in service.list_history()],
                        "pending": service.pending_count(),
                    },
                )
                return
            if path == PurePosixPath("/api/status"):
                latest_history = service.list_history()
                latest = latest_history[0] if latest_history else None
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "backend_ready": service.backend_ready(),
                        "pending": service.pending_count(),
                        "latest": latest.to_dict() if latest else None,
                        "client_id": client_id,
                    },
                )
                return
            self._send_error(HTTPStatus.NOT_FOUND, "未找到接口。")

        def do_POST(self) -> None:
            path = PurePosixPath(self.path.split("?", 1)[0])

            if path == PurePosixPath("/send"):
                if not self._legacy_authorized():
                    self._send_error(HTTPStatus.UNAUTHORIZED, "脚本接口鉴权失败。")
                    return
                payload = self._read_json_payload()
                if payload is None:
                    return
                record = self._submit_legacy_send(payload)
                if record is None:
                    return
                self._send_record(record)
                return

            if path == PurePosixPath("/api/pair/request"):
                client_id = self._require_client_id()
                if client_id is None:
                    return
                request = pairing.request_pair(
                    client_id=client_id,
                    remote_addr=self.client_address[0],
                    user_agent=self.headers.get("User-Agent", ""),
                )
                if request.status == "pending":
                    print(
                        f"\n收到联机请求 [{request.request_id}] ip={request.remote_addr} "
                        f"client={request.client_id}"
                    )
                    print("请在当前终端输入: allow <id> 或 deny <id>")
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    {
                        "ok": True,
                        "request": request.to_dict(),
                    },
                )
                return

            if path == PurePosixPath("/api/pair/logout"):
                client_id = self._require_client_id()
                if client_id is None:
                    return
                pairing.logout(client_id, self._session_token())
                self._send_json(HTTPStatus.OK, {"ok": True})
                return

            client_id = self._require_authorized_session()
            if client_id is None:
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

        def _client_id(self) -> str | None:
            client_id = self.headers.get("X-Client-Id", "").strip()
            return client_id or None

        def _session_token(self) -> str | None:
            token = self.headers.get("X-Session-Token", "").strip()
            return token or None

        def _require_client_id(self) -> str | None:
            client_id = self._client_id()
            if client_id:
                return client_id
            self._send_error(HTTPStatus.BAD_REQUEST, "缺少客户端标识。")
            return None

        def _require_authorized_session(self) -> str | None:
            client_id = self._require_client_id()
            if client_id is None:
                return None
            if not pairing.validate_session(client_id, self._session_token()):
                self._send_error(HTTPStatus.UNAUTHORIZED, "设备未联机或会话已失效。")
                return None
            return client_id

        def _legacy_authorized(self) -> bool:
            if not config.api_token:
                return False
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
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Client-Id, X-Session-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    return ApiHandler


class ApiServer:
    def __init__(self, service: MessageService, config: AppConfig, pairing: PairingManager) -> None:
        handler = create_handler(service, config, pairing)
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
    backend = escape(config.input_backend)
    notifications = "开启" if config.enable_notifications else "关闭"
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
    .warning {{ color: #f59e0b; }}
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
    .hidden {{ display: none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>局域网文字投送</h1>
    </div>

    <div id="pairCard" class="card">
      <div id="pairBanner" class="status muted">设备尚未联机</div>
      <p class="muted">当前网页必须先联机，主控端会在服务终端里确认通过或拒绝。</p>
      <div class="row">
        <button id="pairButton">申请联机</button>
        <button id="refreshPairButton" class="secondary">刷新状态</button>
      </div>
      <div id="pairMeta" class="muted" style="margin-top:12px;"></div>
    </div>

    <div id="controlCard" class="card hidden">
      <textarea id="text" placeholder="输入要投送的文字"></textarea>
      <div class="row">
        <label><input id="autoPaste" type="checkbox"> 自动上屏</label>
        <label><input type="radio" name="shortcut" value="ctrl+v" checked> Ctrl+V</label>
        <label><input type="radio" name="shortcut" value="ctrl+shift+v"> Ctrl+Shift+V</label>
      </div>
      <div class="row">
        <button id="sendButton">发送文本</button>
        <button id="enterButton" class="secondary">发送回车</button>
        <button id="logoutButton" class="secondary">断开联机</button>
      </div>
    </div>

    <div id="statusCard" class="card hidden">
      <div id="banner" class="status muted">等待发送</div>
      <div id="meta" class="muted">后端类型：{backend} · 通知：{notifications}</div>
      <div id="history"></div>
    </div>
  </div>

  <script>
    const pairCard = document.getElementById("pairCard");
    const controlCard = document.getElementById("controlCard");
    const statusCard = document.getElementById("statusCard");
    const pairBanner = document.getElementById("pairBanner");
    const pairMeta = document.getElementById("pairMeta");
    const pairButton = document.getElementById("pairButton");
    const refreshPairButton = document.getElementById("refreshPairButton");
    const logoutButton = document.getElementById("logoutButton");
    const textEl = document.getElementById("text");
    const autoPasteEl = document.getElementById("autoPaste");
    const sendButton = document.getElementById("sendButton");
    const enterButton = document.getElementById("enterButton");
    const banner = document.getElementById("banner");
    const historyEl = document.getElementById("history");

    const storage = window.localStorage;
    let clientId = storage.getItem("network_input_client_id");
    let sessionToken = storage.getItem("network_input_session_token");

    function ensureClientId() {{
      if (clientId) return clientId;
      clientId = (window.crypto?.randomUUID?.() || `client-${{Date.now()}}-${{Math.random().toString(16).slice(2)}}`);
      storage.setItem("network_input_client_id", clientId);
      return clientId;
    }}

    function apiHeaders(extra = {{}}) {{
      const headers = {{
        "X-Client-Id": ensureClientId(),
        ...extra,
      }};
      if (sessionToken) headers["X-Session-Token"] = sessionToken;
      return headers;
    }}

    function selectedShortcut() {{
      return document.querySelector('input[name="shortcut"]:checked').value;
    }}

    function actionLabel(item) {{
      if (item.action === "copy_and_paste") return `复制并自动上屏（${{item.shortcut}}）`;
      if (item.action === "press_key") return "发送回车";
      return "复制到剪贴板";
    }}

    function setBanner(message, kind = "muted") {{
      banner.className = `status ${{kind}}`;
      banner.textContent = message;
    }}

    function setPairBanner(message, kind = "muted") {{
      pairBanner.className = `status ${{kind}}`;
      pairBanner.textContent = message;
    }}

    function applyPairState(payload) {{
      if (payload.state === "authorized") {{
        if (payload.token) {{
          sessionToken = payload.token;
          storage.setItem("network_input_session_token", sessionToken);
        }}
        pairCard.classList.add("hidden");
        controlCard.classList.remove("hidden");
        statusCard.classList.remove("hidden");
        setBanner("设备已联机，可以发送。", "success");
        return true;
      }}
      controlCard.classList.add("hidden");
      statusCard.classList.add("hidden");
      pairCard.classList.remove("hidden");
      if (payload.state === "pending") {{
        setPairBanner(`等待主控端确认（请求 #${{payload.request_id}}）`, "warning");
      }} else if (payload.state === "rejected") {{
        setPairBanner("联机请求已被拒绝，请重新申请。", "error");
      }} else {{
        setPairBanner("设备尚未联机。", "muted");
      }}
      return false;
    }}

    async function fetchJson(url, options = {{}}) {{
      const response = await fetch(url, options);
      return await response.json();
    }}

    async function refreshPairStatus() {{
      const payload = await fetchJson("/api/pair/status", {{
        headers: apiHeaders(),
      }});
      if (!payload.ok) {{
        setPairBanner(payload.error || "联机状态检查失败", "error");
        return false;
      }}
      pairMeta.textContent = `客户端标识：${{ensureClientId()}}`;
      return applyPairState(payload);
    }}

    async function requestPair() {{
      const payload = await fetchJson("/api/pair/request", {{
        method: "POST",
        headers: {{
          ...apiHeaders(),
          "Content-Type": "application/json",
        }},
        body: JSON.stringify({{}}),
      }});
      if (payload.ok) {{
        setPairBanner(`已提交联机请求（#${{payload.request.request_id}}），请等待主控端确认。`, "warning");
      }} else {{
        setPairBanner(payload.error || "联机请求失败", "error");
      }}
      await refreshPairStatus();
    }}

    async function refreshHistory() {{
      const payload = await fetchJson("/api/history", {{
        headers: apiHeaders(),
      }});
      if (!payload.ok) {{
        if (payload.error?.includes("未联机") || payload.error?.includes("会话已失效")) {{
          storage.removeItem("network_input_session_token");
          sessionToken = null;
          await refreshPairStatus();
        }}
        return;
      }}
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

    async function sendJson(url, payload) {{
      return await fetchJson(url, {{
        method: "POST",
        headers: {{
          ...apiHeaders({{"Content-Type": "application/json"}}),
          "Content-Type": "application/json",
        }},
        body: JSON.stringify(payload),
      }});
    }}

    pairButton.addEventListener("click", requestPair);
    refreshPairButton.addEventListener("click", refreshPairStatus);
    logoutButton.addEventListener("click", async () => {{
      await sendJson("/api/pair/logout", {{}});
      storage.removeItem("network_input_session_token");
      sessionToken = null;
      await refreshPairStatus();
    }});

    sendButton.addEventListener("click", async () => {{
      const result = await sendJson("/api/send", {{
        text: textEl.value,
        source: "web",
        auto_paste: autoPasteEl.checked,
        shortcut: selectedShortcut(),
      }});
      if (result.ok) {{
        textEl.value = "";
        const record = result.record;
        if (record.action === "copy_and_paste") {{
          setBanner(`已发送并尝试自动上屏：${{record.shortcut}}`, "success");
        }} else {{
          setBanner("已复制到剪贴板，请手动粘贴。", "success");
        }}
        await refreshHistory();
      }} else {{
        setBanner(result.error || "发送失败", "error");
      }}
    }});

    enterButton.addEventListener("click", async () => {{
      const result = await sendJson("/api/enter", {{}});
      if (result.ok) {{
        setBanner("已发送回车。", "success");
        await refreshHistory();
      }} else {{
        setBanner(result.error || "发送回车失败", "error");
      }}
    }});

    async function boot() {{
      const authorized = await refreshPairStatus();
      if (authorized) {{
        await refreshHistory();
      }}
      setInterval(async () => {{
        const paired = await refreshPairStatus();
        if (paired) {{
          await refreshHistory();
        }}
      }}, 2000);
    }}

    boot();
  </script>
</body>
</html>"""
