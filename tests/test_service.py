from __future__ import annotations

import unittest

from network_input.input_backends import build_wtype_command, build_wtype_release_command
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


class MessageServiceTests(unittest.TestCase):
    def test_submit_processes_messages_in_order(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        self.addCleanup(service.stop)

        service.submit("first", source="test")
        service.submit("second", source="test")

        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.received, ["first", "second"])

        history = service.list_history()
        self.assertEqual([item.text for item in history], ["second", "first"])
        self.assertTrue(all(item.status == "success" for item in history))

    def test_submit_normalizes_newlines_to_spaces(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        self.addCleanup(service.stop)

        service.submit("hello\nworld", source="test")

        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.received, ["hello world"])

    def test_build_wtype_command_normalizes_newlines(self) -> None:
        command = build_wtype_command("hello\nworld")
        self.assertEqual(command, ["wtype", "hello world"])

    def test_build_wtype_release_command_releases_modifiers(self) -> None:
        command = build_wtype_release_command()
        self.assertEqual(
            command,
            [
                "wtype",
                "-m",
                "shift",
                "-m",
                "capslock",
                "-m",
                "ctrl",
                "-m",
                "logo",
                "-m",
                "altgr",
            ],
        )
