from __future__ import annotations

import unittest

from network_input.config import AppConfig
from network_input.runtime import AppRuntime


class RuntimeTests(unittest.TestCase):
    def test_api_is_enabled_by_default(self) -> None:
        runtime = AppRuntime(AppConfig())
        self.addCleanup(runtime.stop)
        runtime.start()

        self.assertIsNotNone(runtime.api)
        self.assertTrue(runtime.web_urls())

    def test_api_can_be_enabled(self) -> None:
        runtime = AppRuntime(AppConfig(host="127.0.0.1", port=0))
        self.addCleanup(runtime.stop)
        runtime.start()

        self.assertIsNotNone(runtime.api)
        self.assertTrue(runtime.api_urls())
