from __future__ import annotations

import unittest
from unittest.mock import patch

from network_input.input_backends import (
    build_wl_copy_command,
    build_wtype_key_command,
    build_wtype_shortcut_command,
)
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

    def test_submit_preserves_newlines_for_clipboard(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        self.addCleanup(service.stop)

        service.submit("hello\nworld", source="test")

        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.received, ["hello\nworld"])

    def test_build_wl_copy_command(self) -> None:
        command = build_wl_copy_command()
        self.assertEqual(command, ["wl-copy"])

    def test_submit_with_auto_paste_queues_shortcut(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        self.addCleanup(service.stop)

        service.submit_with_auto_paste("hello", source="test", shortcut="ctrl+shift+v")

        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.received, ["hello"])
        self.assertEqual(backend.shortcuts, ["ctrl+shift+v"])

    def test_submit_enter_queues_return_key(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        self.addCleanup(service.stop)

        service.submit_enter(source="test")

        self.assertTrue(service.wait_until_idle())
        self.assertEqual(backend.keys, ["Return"])

    def test_build_wtype_shortcut_command_ctrl_v(self) -> None:
        command = build_wtype_shortcut_command("ctrl+v")
        self.assertEqual(command, ["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"])

    def test_build_wtype_shortcut_command_ctrl_shift_v(self) -> None:
        command = build_wtype_shortcut_command("ctrl+shift+v")
        self.assertEqual(
            command,
            ["wtype", "-M", "ctrl", "-M", "shift", "-k", "v", "-m", "shift", "-m", "ctrl"],
        )

    def test_build_wtype_key_command_return(self) -> None:
        command = build_wtype_key_command("enter")
        self.assertEqual(command, ["wtype", "-k", "Return"])

    def test_notifications_are_disabled_by_default(self) -> None:
        backend = RecordingBackend()
        service = MessageService(backend, max_history=5)
        service.start()
        self.addCleanup(service.stop)

        with patch("network_input.service.notify_clipboard_updated") as mocked_notify:
            service.submit("hello", source="test")
            self.assertTrue(service.wait_until_idle())

        mocked_notify.assert_not_called()
