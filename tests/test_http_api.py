from __future__ import annotations

import json
import urllib.error
import urllib.request
import unittest

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
    def test_send_endpoint_accepts_json(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        server = ApiServer(service, AppConfig(host="127.0.0.1", port=0))
        server.start()
        self.addCleanup(server.stop)
        self.addCleanup(service.stop)

        body = json.dumps({"text": "hello", "source": "test"}).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/send",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.received, ["hello"])

    def test_send_endpoint_rejects_missing_token(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        server = ApiServer(
            service,
            AppConfig(host="127.0.0.1", port=0, api_token="secret-token"),
        )
        server.start()
        self.addCleanup(server.stop)
        self.addCleanup(service.stop)

        body = json.dumps({"text": "hello"}).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/send",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=2)

        self.assertEqual(context.exception.code, 401)

    def test_root_page_serves_html(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        server = ApiServer(service, AppConfig(host="127.0.0.1", port=0))
        server.start()
        self.addCleanup(server.stop)
        self.addCleanup(service.stop)

        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=2) as response:
            body = response.read().decode("utf-8")

        self.assertIn("局域网文字投送", body)
        self.assertIn("发送回车", body)

    def test_web_send_endpoint_supports_auto_paste(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        server = ApiServer(service, AppConfig(host="127.0.0.1", port=0))
        server.start()
        self.addCleanup(server.stop)
        self.addCleanup(service.stop)

        body = json.dumps(
            {"text": "hello", "source": "web", "auto_paste": True, "shortcut": "ctrl+shift+v"}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/api/send",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.received, ["hello"])
        self.assertEqual(backend.shortcuts, ["ctrl+shift+v"])

    def test_enter_endpoint_sends_return_key(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        server = ApiServer(service, AppConfig(host="127.0.0.1", port=0))
        server.start()
        self.addCleanup(server.stop)
        self.addCleanup(service.stop)

        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/api/enter",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.keys, ["Return"])
