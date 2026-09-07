from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from rag_service.answer import Citation
from rag_service.context import ContextBlock, ContextPack
from rag_service.retrieval import RetrievalCandidate


@dataclass
class CheckpointHandle:
    saver: Any
    backend: str
    _close: Callable[[], None]
    _ping: Callable[[], bool]
    resource: Any = None

    def close(self) -> None:
        self._close()

    def ping(self) -> bool:
        return self._ping()


def create_sqlite_checkpointer(path: str) -> CheckpointHandle:
    """Create a sync SQLite saver with an explicit deserialization allowlist."""
    if path != ":memory:":
        Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=(RetrievalCandidate, Citation, ContextBlock, ContextPack),
    )
    saver = SqliteSaver(connection, serde=serializer)
    saver.setup()
    def ping() -> bool:
        return bool(connection.execute("SELECT 1").fetchone())

    return CheckpointHandle(
        saver=saver,
        backend="sqlite",
        _close=connection.close,
        _ping=ping,
        resource=connection,
    )


def open_sqlite_checkpointer_readonly(path: str) -> CheckpointHandle:
    """Open an existing SQLite checkpoint database without mutating the source file."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"SQLite checkpoint database does not exist: {resolved}")
    connection = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True, check_same_thread=False)
    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=(RetrievalCandidate, Citation, ContextBlock, ContextPack),
    )
    saver = SqliteSaver(connection, serde=serializer)
    saver.is_setup = True

    def ping() -> bool:
        return bool(connection.execute("SELECT 1").fetchone())

    return CheckpointHandle(
        saver=saver,
        backend="sqlite",
        _close=connection.close,
        _ping=ping,
        resource=connection,
    )


def create_postgres_checkpointer(
    database_url: str,
    *,
    min_size: int,
    max_size: int,
    timeout_seconds: float,
    setup: bool = False,
) -> CheckpointHandle:
    """Create a pooled production checkpointer without importing drivers at module load."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout_seconds,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    try:
        serializer = JsonPlusSerializer(
            allowed_msgpack_modules=(RetrievalCandidate, Citation, ContextBlock, ContextPack),
        )
        saver = PostgresSaver(pool, serde=serializer)
        if setup:
            saver.setup()

        def ping() -> bool:
            with pool.connection(timeout=timeout_seconds) as connection:
                return bool(connection.execute("SELECT 1").fetchone())

        return CheckpointHandle(
            saver=saver,
            backend="postgres",
            _close=pool.close,
            _ping=ping,
            resource=pool,
        )
    except Exception:
        pool.close()
        raise


def create_checkpointer(settings, *, setup: bool = False) -> CheckpointHandle:
    if settings.state_backend == "sqlite":
        return create_sqlite_checkpointer(settings.checkpoint_path)
    if not settings.database_url:
        raise ValueError("RAG_DATABASE_URL is required for the postgres state backend")
    return create_postgres_checkpointer(
        settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        timeout_seconds=settings.db_pool_timeout_seconds,
        setup=setup,
    )
