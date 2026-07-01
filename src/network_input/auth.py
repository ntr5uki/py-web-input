from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import secrets
import threading


@dataclass(slots=True)
class PairRequest:
    request_id: int
    client_id: str
    remote_addr: str
    user_agent: str
    created_at: datetime
    status: str = "pending"
    decided_at: datetime | None = None
    session_token: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "request_id": self.request_id,
            "client_id": self.client_id,
            "remote_addr": self.remote_addr,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "session_token": self.session_token,
        }


@dataclass(slots=True)
class AuthorizedSession:
    token: str
    client_id: str
    remote_addr: str
    approved_on: date
    approved_at: datetime


class PairingManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_request_id = 1
        self._requests: dict[int, PairRequest] = {}
        self._sessions: dict[str, AuthorizedSession] = {}

    def request_pair(self, client_id: str, remote_addr: str, user_agent: str) -> PairRequest:
        with self._lock:
            self._prune_sessions_locked()
            existing = self._find_latest_request_locked(client_id)
            if existing and existing.status == "pending":
                return existing
            if existing and existing.status == "approved" and existing.session_token:
                session = self._sessions.get(existing.session_token)
                if session and session.client_id == client_id and session.approved_on == self._today():
                    return existing

            request = PairRequest(
                request_id=self._next_request_id,
                client_id=client_id,
                remote_addr=remote_addr,
                user_agent=user_agent,
                created_at=datetime.now(timezone.utc),
            )
            self._requests[request.request_id] = request
            self._next_request_id += 1
            return request

    def get_pair_status(self, client_id: str, session_token: str | None) -> dict[str, str | int | None]:
        with self._lock:
            self._prune_sessions_locked()
            session = self._validate_session_locked(client_id, session_token)
            if session:
                return {
                    "state": "authorized",
                    "token": session.token,
                    "approved_on": session.approved_on.isoformat(),
                }

            request = self._find_latest_request_locked(client_id)
            if request is None:
                return {"state": "unpaired"}
            if request.status == "approved" and request.session_token:
                session = self._sessions.get(request.session_token)
                if session and session.approved_on == self._today():
                    return {
                        "state": "authorized",
                        "token": session.token,
                        "approved_on": session.approved_on.isoformat(),
                    }
                return {"state": "unpaired"}
            return {
                "state": request.status,
                "request_id": request.request_id,
            }

    def validate_session(self, client_id: str, session_token: str | None) -> bool:
        with self._lock:
            self._prune_sessions_locked()
            return self._validate_session_locked(client_id, session_token) is not None

    def approve_request(self, request_id: int) -> PairRequest:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise KeyError(f"未找到请求 {request_id}")
            token = secrets.token_urlsafe(24)
            request.status = "approved"
            request.session_token = token
            request.decided_at = datetime.now(timezone.utc)
            self._sessions[token] = AuthorizedSession(
                token=token,
                client_id=request.client_id,
                remote_addr=request.remote_addr,
                approved_on=self._today(),
                approved_at=datetime.now(timezone.utc),
            )
            return request

    def reject_request(self, request_id: int) -> PairRequest:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise KeyError(f"未找到请求 {request_id}")
            request.status = "rejected"
            request.decided_at = datetime.now(timezone.utc)
            return request

    def list_pending_requests(self) -> list[PairRequest]:
        with self._lock:
            return [item for item in self._requests.values() if item.status == "pending"]

    def list_requests(self) -> list[PairRequest]:
        with self._lock:
            return list(sorted(self._requests.values(), key=lambda item: item.request_id, reverse=True))

    def logout(self, client_id: str, session_token: str | None) -> None:
        with self._lock:
            session = self._validate_session_locked(client_id, session_token)
            if not session:
                return
            self._sessions.pop(session.token, None)
            request = self._find_latest_request_locked(client_id)
            if request and request.session_token == session.token and request.status == "approved":
                request.status = "logged_out"

    def _find_latest_request_locked(self, client_id: str) -> PairRequest | None:
        candidates = [item for item in self._requests.values() if item.client_id == client_id]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.request_id)

    def _validate_session_locked(self, client_id: str, session_token: str | None) -> AuthorizedSession | None:
        if not session_token:
            return None
        session = self._sessions.get(session_token)
        if session is None:
            return None
        if session.client_id != client_id:
            return None
        if session.approved_on != self._today():
            self._sessions.pop(session_token, None)
            return None
        return session

    def _prune_sessions_locked(self) -> None:
        today = self._today()
        expired = [token for token, session in self._sessions.items() if session.approved_on != today]
        for token in expired:
            self._sessions.pop(token, None)

    def _today(self) -> date:
        return datetime.now().date()
