from __future__ import annotations

import atexit
import socket
import threading

from .auth import PairingManager
from .config import AppConfig
from .http_api import ApiServer
from .input_backends import create_input_backend
from .service import MessageService


class AppRuntime:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.backend = create_input_backend(config.input_backend)
        self.pairing = PairingManager()
        self.service = MessageService(
            self.backend,
            max_history=config.max_history,
            enable_notifications=config.enable_notifications,
        )
        self.api = ApiServer(self.service, config, self.pairing)
        self._started = False
        self._stop_event = threading.Event()

    def start(self) -> "AppRuntime":
        if self._started:
            return self
        self.service.start()
        self.api.start()
        self._started = True
        atexit.register(self.stop)
        return self

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        self.api.stop()
        self.service.stop()
        self._started = False

    def api_urls(self) -> list[str]:
        urls = [f"http://127.0.0.1:{self.api.port}/send"]
        for address in _lan_ipv4_addresses():
            urls.append(f"http://{address}:{self.api.port}/send")
        return list(dict.fromkeys(urls))

    def web_urls(self) -> list[str]:
        urls = [f"http://127.0.0.1:{self.api.port}/"]
        for address in _lan_ipv4_addresses():
            urls.append(f"http://{address}:{self.api.port}/")
        return list(dict.fromkeys(urls))

    def wait_forever(self) -> None:
        self._stop_event.wait()


def _lan_ipv4_addresses() -> list[str]:
    addresses: list[str] = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET)
    except OSError:
        infos = []

    for info in infos:
        address = info[4][0]
        if address.startswith("127."):
            continue
        addresses.append(address)
    return addresses
