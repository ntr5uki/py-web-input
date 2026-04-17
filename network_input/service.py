from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
import queue
import threading
import time

from .input_backends import InputBackend
from .models import MessageRecord, MessageStatus
from .notifications import notify_clipboard_updated


class MessageService:
    def __init__(
        self,
        backend: InputBackend,
        max_history: int = 20,
        enable_notifications: bool = False,
    ) -> None:
        self._backend = backend
        self._history: deque[MessageRecord] = deque(maxlen=max_history)
        self._queue: queue.Queue[MessageRecord] = queue.Queue()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._enable_notifications = enable_notifications

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run,
            name="message-service-worker",
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=1)

    def submit(self, text: str, source: str) -> MessageRecord:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("文本内容不能为空。")

        record = MessageRecord.new(text=normalized, source=source)
        with self._lock:
            self._history.append(record)
        self._queue.put(record)
        return replace(record)

    def submit_with_auto_paste(self, text: str, source: str, shortcut: str) -> MessageRecord:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("文本内容不能为空。")

        record = MessageRecord.new(
            text=normalized,
            source=source,
            action="copy_and_paste",
            shortcut=shortcut,
        )
        with self._lock:
            self._history.append(record)
        self._queue.put(record)
        return replace(record)

    def submit_enter(self, source: str) -> MessageRecord:
        record = MessageRecord.new(
            text="发送回车",
            source=source,
            action="press_key",
            shortcut="Return",
        )
        with self._lock:
            self._history.append(record)
        self._queue.put(record)
        return replace(record)

    def list_history(self) -> list[MessageRecord]:
        with self._lock:
            return [replace(item) for item in reversed(self._history)]

    def backend_ready(self) -> bool:
        return self._backend.is_available()

    def pending_count(self) -> int:
        return self._queue.qsize()

    def wait_until_idle(self, timeout: float = 3) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                record = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            with self._lock:
                record.status = MessageStatus.PROCESSING

            try:
                if record.action == "copy":
                    self._backend.inject(record.text)
                elif record.action == "copy_and_paste":
                    self._backend.inject(record.text)
                    self._backend.press_shortcut(record.shortcut or "ctrl+v")
                elif record.action == "press_key":
                    self._backend.press_key(record.shortcut or "Return")
                else:
                    raise ValueError(f"未知动作: {record.action}")
            except Exception as exc:
                with self._lock:
                    record.status = MessageStatus.FAILED
                    record.error = str(exc)
                    record.processed_at = datetime.now(timezone.utc)
            else:
                with self._lock:
                    record.status = MessageStatus.SUCCESS
                    record.processed_at = datetime.now(timezone.utc)
                if self._enable_notifications and record.action in {"copy", "copy_and_paste"}:
                    notify_clipboard_updated(record.text)
            finally:
                self._queue.task_done()
