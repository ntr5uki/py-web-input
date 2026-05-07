from __future__ import annotations

import ctypes
import unittest
from unittest.mock import patch

from network_input.input_backends import (
    ClipboardBackend,
    EXPECTED_INPUT_SIZE,
    INPUT,
    VK_CONTROL,
    VK_RETURN,
    VK_SHIFT,
    VK_V,
    WindowsBackend,
    build_windows_key_events,
    build_windows_shortcut_events,
    create_input_backend,
)


def event_tuples(events: list[object]) -> list[tuple[int, bool]]:
    return [(event.vk, event.key_up) for event in events]


class InputBackendSelectionTests(unittest.TestCase):
    def test_auto_selects_windows_on_win32(self) -> None:
        with patch("network_input.input_backends.sys.platform", "win32"):
            backend = create_input_backend("auto", windows_paste_delay_ms=12)

        self.assertIsInstance(backend, WindowsBackend)

    def test_auto_selects_clipboard_backend_off_windows(self) -> None:
        with patch("network_input.input_backends.sys.platform", "linux"):
            backend = create_input_backend("auto")

        self.assertIsInstance(backend, ClipboardBackend)

    def test_windows_backend_rejects_non_windows_platform(self) -> None:
        with patch("network_input.input_backends.sys.platform", "linux"):
            with self.assertRaisesRegex(ValueError, "Windows 输入后端只能在 Windows 上使用"):
                create_input_backend("windows")

    def test_unknown_backend_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "不支持的输入后端"):
            create_input_backend("unknown")


class WindowsBackendEventTests(unittest.TestCase):
    def test_sendinput_structure_size_matches_windows_api(self) -> None:
        self.assertEqual(ctypes.sizeof(INPUT), EXPECTED_INPUT_SIZE)

    def test_ctrl_v_event_sequence(self) -> None:
        events = build_windows_shortcut_events("ctrl+v")

        self.assertEqual(
            event_tuples(events),
            [
                (VK_CONTROL, False),
                (VK_V, False),
                (VK_V, True),
                (VK_CONTROL, True),
            ],
        )

    def test_ctrl_shift_v_event_sequence(self) -> None:
        events = build_windows_shortcut_events("ctrl+shift+v")

        self.assertEqual(
            event_tuples(events),
            [
                (VK_CONTROL, False),
                (VK_SHIFT, False),
                (VK_V, False),
                (VK_V, True),
                (VK_SHIFT, True),
                (VK_CONTROL, True),
            ],
        )

    def test_enter_event_sequence(self) -> None:
        events = build_windows_key_events("Return")

        self.assertEqual(event_tuples(events), [(VK_RETURN, False), (VK_RETURN, True)])

    def test_inject_delegates_to_windows_clipboard_writer(self) -> None:
        backend = WindowsBackend()

        with patch("network_input.input_backends._set_windows_clipboard_text") as mocked_set_clipboard:
            backend.inject("你好 Windows")

        mocked_set_clipboard.assert_called_once_with("你好 Windows")

    def test_press_shortcut_uses_delay_and_sendinput_path(self) -> None:
        backend = WindowsBackend(paste_delay_ms=12)

        with (
            patch("network_input.input_backends.time.sleep") as mocked_sleep,
            patch("network_input.input_backends._send_windows_key_events") as mocked_send,
        ):
            backend.press_shortcut("ctrl+v")

        mocked_sleep.assert_called_once_with(0.012)
        sent_events = mocked_send.call_args.args[0]
        self.assertEqual(
            event_tuples(sent_events),
            [
                (VK_CONTROL, False),
                (VK_V, False),
                (VK_V, True),
                (VK_CONTROL, True),
            ],
        )


if __name__ == "__main__":
    unittest.main()
