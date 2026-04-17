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

    def is_available(self) -> bool:
        return True

    def describe(self) -> str:
        return "recording"

    def inject(self, text: str) -> None:
        self.received.append(text)


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
