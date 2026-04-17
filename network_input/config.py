from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(slots=True)
class AppConfig:
    host: str = "0.0.0.0"
    port: int = 18502
    enable_notifications: bool = False
    max_history: int = 20
    api_token: str | None = None
    input_backend: str = "clipboard"

    @classmethod
    def from_env(cls) -> "AppConfig":
        api_token = os.getenv("NETWORK_INPUT_API_TOKEN", "").strip() or None
        return cls(
            host=os.getenv("NETWORK_INPUT_HOST", "0.0.0.0"),
            port=int(os.getenv("NETWORK_INPUT_PORT", "18502")),
            enable_notifications=_env_bool("NETWORK_INPUT_ENABLE_NOTIFICATIONS", default=False),
            max_history=int(os.getenv("NETWORK_INPUT_MAX_HISTORY", "20")),
            api_token=api_token,
            input_backend=os.getenv("NETWORK_INPUT_BACKEND", "clipboard").strip() or "clipboard",
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
