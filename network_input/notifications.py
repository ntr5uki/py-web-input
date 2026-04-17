from __future__ import annotations

import shutil
import subprocess


def notify_clipboard_updated(text: str) -> None:
    if shutil.which("notify-send") is None:
        return

    body = build_notification_body(text)
    try:
        subprocess.run(
            ["notify-send", "局域网文字投送", body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=3,
        )
    except Exception:
        return


def build_notification_body(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= 60:
        preview = normalized
    else:
        preview = f"{normalized[:57]}..."
    return f"已复制到剪贴板，请手动粘贴。\n{preview}"
