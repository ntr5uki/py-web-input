from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
from datetime import datetime, timezone
from enum import StrEnum
import uuid


class MessageStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(slots=True)
class MessageRecord:
    message_id: str
    text: str
    source: str
    received_at: datetime
    status: MessageStatus
    action: str = "copy"
    shortcut: str | None = None
    processed_at: datetime | None = None
    error: str | None = None

    @classmethod
    def new(
        cls,
        text: str,
        source: str,
        *,
        action: str = "copy",
        shortcut: str | None = None,
    ) -> "MessageRecord":
        return cls(
            message_id=uuid.uuid4().hex[:10],
            text=text,
            source=source,
            received_at=datetime.now(timezone.utc),
            status=MessageStatus.QUEUED,
            action=action,
            shortcut=shortcut,
        )

    def to_dict(self) -> dict[str, str | None]:
        payload = asdict(self)
        payload["received_at"] = self.received_at.isoformat()
        payload["processed_at"] = self.processed_at.isoformat() if self.processed_at else None
        payload["status"] = self.status.value
        return payload
