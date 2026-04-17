from __future__ import annotations

import unittest

from network_input.notifications import build_notification_body


class NotificationTests(unittest.TestCase):
    def test_build_notification_body_short_text(self) -> None:
        body = build_notification_body("hello world")
        self.assertIn("已复制到剪贴板，请手动粘贴。", body)
        self.assertIn("hello world", body)

    def test_build_notification_body_truncates_long_text(self) -> None:
        body = build_notification_body("a" * 80)
        self.assertTrue(body.endswith("..."))
