from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any

from .config import AppConfig
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
            if self.path != "/health":
                self._send_error(HTTPStatus.NOT_FOUND, "未找到接口。")
                return

            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "backend_ready": service.backend_ready(),
                    "pending": service.pending_count(),
                },
            )

        def do_POST(self) -> None:
            if self.path != "/send":
                self._send_error(HTTPStatus.NOT_FOUND, "未找到接口。")
                return

            if not self._authorized():
                self._send_error(HTTPStatus.UNAUTHORIZED, "鉴权失败。")
                return

            content_length = int(self.headers.get("Content-Length", "0") or 0)
            if content_length <= 0 or content_length > 64_000:
                self._send_error(HTTPStatus.BAD_REQUEST, "请求体大小不合法。")
                return

            try:
                payload = json.loads(self.rfile.read(content_length))
            except json.JSONDecodeError:
                self._send_error(HTTPStatus.BAD_REQUEST, "请求体不是合法 JSON。")
                return

            text = payload.get("text")
            source = payload.get("source", "api")
            if not isinstance(text, str):
                self._send_error(HTTPStatus.BAD_REQUEST, "`text` 必须是字符串。")
                return
            if not isinstance(source, str):
                source = "api"

            try:
                record = service.submit(text=text, source=source)
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return

            self._send_json(
                HTTPStatus.ACCEPTED,
                {
                    "ok": True,
                    "message_id": record.message_id,
                    "status": record.status,
                    "received_at": record.received_at.isoformat(),
                },
            )

        def log_message(self, format: str, *args: Any) -> None:
            return

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
