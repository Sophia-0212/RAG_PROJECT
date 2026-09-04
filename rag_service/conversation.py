from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ConversationAccessError(PermissionError):
    """Raised when a conversation is owned by a different user."""


class ThreadDeleter(Protocol):
    def delete_thread(self, thread_id: str) -> None: ...


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    tenant_id: str
    user_id: str
    thread_id: str
    summary: str
    updated_at_ms: int
    expires_at_ms: int


def scoped_thread_id(tenant_id: str, conversation_id: str) -> str:
    payload = f"{tenant_id}\0{conversation_id}".encode("utf-8")
    return f"rag-{hashlib.sha256(payload).hexdigest()}"


class ConversationStore:
    """Tenant-bound conversation metadata with explicit expiry semantics."""

    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._setup()

    def _setup(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_conversations (
                    tenant_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL DEFAULT '',
                    updated_at_ms INTEGER NOT NULL,
                    expires_at_ms INTEGER NOT NULL,
                    PRIMARY KEY (tenant_id, conversation_id)
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_conversations_expiry "
                "ON rag_conversations(expires_at_ms)"
            )

    @staticmethod
    def _validate_identity(conversation_id: str, tenant_id: str, user_id: str) -> None:
        if not conversation_id.strip() or not tenant_id.strip() or not user_id.strip():
            raise ValueError("conversation_id, tenant_id, and user_id are required")

    def claim(
        self,
        conversation_id: str,
        *,
        tenant_id: str,
        user_id: str,
        ttl_seconds: int,
        now_ms: int | None = None,
    ) -> ConversationRecord:
        self._validate_identity(conversation_id, tenant_id, user_id)
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        current_ms = int(time.time() * 1000) if now_ms is None else now_ms
        expires_at_ms = current_ms + ttl_seconds * 1000
        thread_id = scoped_thread_id(tenant_id, conversation_id)
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM rag_conversations WHERE tenant_id = ? AND conversation_id = ?",
                (tenant_id, conversation_id),
            ).fetchone()
            if row is not None and row["user_id"] != user_id:
                raise ConversationAccessError("conversation belongs to a different user")
            if row is None:
                self._connection.execute(
                    """
                    INSERT INTO rag_conversations
                    (tenant_id, conversation_id, user_id, thread_id, updated_at_ms, expires_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tenant_id, conversation_id, user_id, thread_id, current_ms, expires_at_ms),
                )
            else:
                self._connection.execute(
                    """
                    UPDATE rag_conversations
                    SET updated_at_ms = ?, expires_at_ms = ?
                    WHERE tenant_id = ? AND conversation_id = ?
                    """,
                    (current_ms, expires_at_ms, tenant_id, conversation_id),
                )
        return self.get(conversation_id, tenant_id=tenant_id, user_id=user_id, now_ms=current_ms)

    def get(
        self,
        conversation_id: str,
        *,
        tenant_id: str,
        user_id: str,
        now_ms: int | None = None,
    ) -> ConversationRecord:
        self._validate_identity(conversation_id, tenant_id, user_id)
        current_ms = int(time.time() * 1000) if now_ms is None else now_ms
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM rag_conversations WHERE tenant_id = ? AND conversation_id = ?",
                (tenant_id, conversation_id),
            ).fetchone()
        if row is None or int(row["expires_at_ms"]) <= current_ms:
            raise KeyError("conversation does not exist or has expired")
        if row["user_id"] != user_id:
            raise ConversationAccessError("conversation belongs to a different user")
        return ConversationRecord(**dict(row))

    def append_turn(
        self,
        conversation_id: str,
        *,
        tenant_id: str,
        user_id: str,
        question: str,
        answer: str,
        ttl_seconds: int,
        max_chars: int,
        now_ms: int | None = None,
    ) -> ConversationRecord:
        if max_chars <= 0:
            raise ValueError("max_chars must be greater than zero")
        record = self.claim(
            conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            ttl_seconds=ttl_seconds,
            now_ms=now_ms,
        )
        turn = f"User: {question.strip()}\nAssistant: {answer.strip()}".strip()
        summary = f"{record.summary}\n{turn}".strip()[-max_chars:]
        current_ms = int(time.time() * 1000) if now_ms is None else now_ms
        expires_at_ms = current_ms + ttl_seconds * 1000
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE rag_conversations
                SET summary = ?, updated_at_ms = ?, expires_at_ms = ?
                WHERE tenant_id = ? AND conversation_id = ? AND user_id = ?
                """,
                (summary, current_ms, expires_at_ms, tenant_id, conversation_id, user_id),
            )
        return self.get(conversation_id, tenant_id=tenant_id, user_id=user_id, now_ms=current_ms)

    def prune_expired(self, checkpointer: ThreadDeleter, *, now_ms: int | None = None) -> int:
        current_ms = int(time.time() * 1000) if now_ms is None else now_ms
        with self._lock:
            rows = self._connection.execute(
                "SELECT tenant_id, conversation_id, thread_id FROM rag_conversations WHERE expires_at_ms <= ?",
                (current_ms,),
            ).fetchall()
        for row in rows:
            checkpointer.delete_thread(str(row["thread_id"]))
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM rag_conversations WHERE expires_at_ms <= ?",
                (current_ms,),
            )
        return len(rows)

    def delete(
        self,
        conversation_id: str,
        *,
        tenant_id: str,
        user_id: str,
        checkpointer: ThreadDeleter,
    ) -> bool:
        self._validate_identity(conversation_id, tenant_id, user_id)
        with self._lock:
            row = self._connection.execute(
                "SELECT user_id, thread_id FROM rag_conversations WHERE tenant_id = ? AND conversation_id = ?",
                (tenant_id, conversation_id),
            ).fetchone()
        if row is None:
            return False
        if row["user_id"] != user_id:
            raise ConversationAccessError("conversation belongs to a different user")
        checkpointer.delete_thread(str(row["thread_id"]))
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM rag_conversations WHERE tenant_id = ? AND conversation_id = ?",
                (tenant_id, conversation_id),
            )
        return True

    def ping(self) -> bool:
        with self._lock:
            row = self._connection.execute("SELECT 1").fetchone()
        return bool(row and row[0] == 1)

    def close(self) -> None:
        self._connection.close()
