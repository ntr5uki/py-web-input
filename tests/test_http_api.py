from __future__ import annotations

import json
import urllib.error
import urllib.request
import unittest

from network_input.auth import PairingManager
from network_input.config import AppConfig
from network_input.http_api import ApiServer
from network_input.service import MessageService


class RecordingBackend:
    def __init__(self) -> None:
        self.received: list[str] = []
        self.shortcuts: list[str] = []
        self.keys: list[str] = []

    def is_available(self) -> bool:
        return True

    def describe(self) -> str:
        return "recording"

    def inject(self, text: str) -> None:
        self.received.append(text)

    def press_shortcut(self, shortcut: str) -> None:
        self.shortcuts.append(shortcut)

    def press_key(self, key: str) -> None:
        self.keys.append(key)


class HttpApiTests(unittest.TestCase):
    def start_server(
        self,
        *,
        api_token: str | None = None,
    ) -> tuple[RecordingBackend, MessageService, ApiServer, PairingManager]:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        pairing = PairingManager()
        service.start()
        server = ApiServer(
            service,
            AppConfig(host="127.0.0.1", port=0, api_token=api_token),
            pairing,
        )
        server.start()
        self.addCleanup(server.stop)
        self.addCleanup(service.stop)
        return backend, service, server, pairing

    def request_json(
        self,
        server: ApiServer,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        data = None
        final_headers = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            final_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}{path}",
            data=data,
            headers=final_headers,
            method=method,
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_root_page_serves_pairing_html(self) -> None:
        _, _, server, _ = self.start_server()

        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=2) as response:
            body = response.read().decode("utf-8")

        self.assertIn("局域网文字投送", body)
        self.assertIn("申请联机", body)
        self.assertIn("发送回车", body)

    def test_pair_status_requires_client_id(self) -> None:
        _, _, server, _ = self.start_server()

        request = urllib.request.Request(f"http://127.0.0.1:{server.port}/api/pair/status")
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=2)

        self.assertEqual(context.exception.code, 400)

    def test_protected_endpoints_reject_unpaired_client(self) -> None:
        _, _, server, _ = self.start_server()

        for path in ("/api/send", "/api/enter"):
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.port}{path}",
                data=b"{}",
                headers={"Content-Type": "application/json", "X-Client-Id": "client-a"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(context.exception.code, 401)

    def test_pair_request_then_send_and_enter_after_approval(self) -> None:
        backend, service, server, pairing = self.start_server()
        client_id = "client-a"

        pair_response = self.request_json(
            server,
            "/api/pair/request",
            method="POST",
            body={},
            headers={"X-Client-Id": client_id},
        )
        self.assertTrue(pair_response["ok"])
        request_id = int(pair_response["request"]["request_id"])

        pairing.approve_request(request_id)
        status_payload = self.request_json(
            server,
            "/api/pair/status",
            headers={"X-Client-Id": client_id},
        )
        self.assertEqual(status_payload["state"], "authorized")
        session_token = str(status_payload["token"])

        send_payload = self.request_json(
            server,
            "/api/send",
            method="POST",
            body={
                "text": "hello",
                "source": "web",
                "auto_paste": True,
                "shortcut": "ctrl+shift+v",
            },
            headers={
                "X-Client-Id": client_id,
                "X-Session-Token": session_token,
            },
        )
        self.assertTrue(send_payload["ok"])

        enter_payload = self.request_json(
            server,
            "/api/enter",
            method="POST",
            body={},
            headers={
                "X-Client-Id": client_id,
                "X-Session-Token": session_token,
            },
        )
        self.assertTrue(enter_payload["ok"])

        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.received, ["hello"])
        self.assertEqual(backend.shortcuts, ["ctrl+shift+v"])
        self.assertEqual(backend.keys, ["Return"])

    def test_send_endpoint_rejects_missing_token(self) -> None:
        _, _, server, _ = self.start_server(api_token="secret-token")

        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/send",
            data=json.dumps({"text": "hello"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=2)

        self.assertEqual(context.exception.code, 401)

    def test_send_endpoint_accepts_bearer_token(self) -> None:
        backend, service, server, _ = self.start_server(api_token="secret-token")

        payload = self.request_json(
            server,
            "/send",
            method="POST",
            body={"text": "hello", "source": "test"},
            headers={"Authorization": "Bearer secret-token"},
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.received, ["hello"])
