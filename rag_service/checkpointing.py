from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from rag_service.answer import Citation
from rag_service.context import ContextBlock, ContextPack
from rag_service.retrieval import RetrievalCandidate


@dataclass
class CheckpointHandle:
    saver: SqliteSaver
    connection: sqlite3.Connection

    def close(self) -> None:
        self.connection.close()


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
    return CheckpointHandle(saver=saver, connection=connection)
