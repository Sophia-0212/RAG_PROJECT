from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from rag_service.checkpointing import (
    create_checkpointer,
    create_sqlite_checkpointer,
    open_sqlite_checkpointer_readonly,
)
from rag_service.conversation import ConversationStore, PostgresConversationStore
from rag_service.settings import Settings, get_settings
from rag_service.run_store import PostgresRequestRunStore


def migrate_local_state(path: str) -> dict[str, str]:
    """Create or migrate local checkpoint and conversation schemas idempotently."""
    checkpoints = create_sqlite_checkpointer(path)
    conversations = ConversationStore(path)
    try:
        conversations.prune_expired(checkpoints.saver)
        if not conversations.ping():
            raise RuntimeError("conversation schema verification failed")
        return {"checkpoint": "ready", "conversation": "ready"}
    finally:
        conversations.close()
        checkpoints.close()


def migrate_postgres_state(settings: Settings) -> dict[str, str]:
    if settings.state_backend != "postgres":
        raise ValueError("postgres schema migration requires RAG_STATE_BACKEND=postgres")
    checkpoints = create_checkpointer(settings, setup=True)
    try:
        PostgresConversationStore.setup(checkpoints.resource)
        PostgresRequestRunStore.setup(checkpoints.resource)
        conversations = PostgresConversationStore(checkpoints.resource)
        runs = PostgresRequestRunStore(checkpoints.resource)
        if not checkpoints.ping() or not conversations.ping() or not runs.ping():
            raise RuntimeError("postgres state schema verification failed")
        return {"checkpoint": "ready", "conversation": "ready", "request_runs": "ready"}
    finally:
        checkpoints.close()


def _source_inventory(connection) -> dict[str, int]:
    names = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    return {
        "conversations": (
            int(connection.execute("SELECT COUNT(*) FROM rag_conversations").fetchone()[0])
            if "rag_conversations" in names
            else 0
        ),
        "checkpoints": int(connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]),
        "pending_writes": (
            int(connection.execute("SELECT COUNT(*) FROM writes").fetchone()[0]) if "writes" in names else 0
        ),
        "threads": int(connection.execute("SELECT COUNT(DISTINCT thread_id) FROM checkpoints").fetchone()[0]),
    }


def inspect_sqlite_state(path: str) -> dict[str, Any]:
    source = open_sqlite_checkpointer_readonly(path)
    try:
        inventory = _source_inventory(source.resource)
        return {
            "mode": "dry-run",
            "source": str(Path(path).expanduser().resolve()),
            **inventory,
        }
    finally:
        source.close()


def migrate_sqlite_to_postgres(path: str, settings: Settings) -> dict[str, Any]:
    """Replay SQLite state into PostgreSQL; safe to repeat after an interrupted run."""
    if settings.state_backend != "postgres":
        raise ValueError("state migration requires RAG_STATE_BACKEND=postgres")
    source = open_sqlite_checkpointer_readonly(path)
    target = create_checkpointer(settings, setup=True)
    migration_id: str | None = None
    inventory: dict[str, int] = {}
    try:
        PostgresConversationStore.setup(target.resource)
        inventory = _source_inventory(source.resource)
        source_path = Path(path).expanduser().resolve()
        source_stat = source_path.stat()
        fingerprint_payload = json.dumps(
            {
                "path": str(source_path),
                "size": source_stat.st_size,
                "mtime_ns": source_stat.st_mtime_ns,
                "inventory": inventory,
            },
            sort_keys=True,
        )
        source_fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()
        migration_id = f"sqlite-{source_fingerprint[:24]}"
        with target.resource.connection() as connection, connection.transaction():
            connection.execute(
                """
                INSERT INTO rag_state_migration_runs (migration_id, source_fingerprint, status, details)
                VALUES (%s, %s, 'running', %s::jsonb)
                ON CONFLICT (migration_id) DO UPDATE SET
                    status = 'running', details = EXCLUDED.details, completed_at = NULL
                """,
                (migration_id, source_fingerprint, json.dumps(inventory, sort_keys=True)),
            )
        source_tables = {
            row[0]
            for row in source.resource.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if "rag_conversations" in source_tables:
            rows = source.resource.execute(
                "SELECT tenant_id, conversation_id, user_id, thread_id, summary, updated_at_ms, expires_at_ms "
                "FROM rag_conversations"
            ).fetchall()
            with target.resource.connection() as connection, connection.transaction():
                for row in rows:
                    existing = connection.execute(
                        "SELECT user_id FROM rag_conversations WHERE tenant_id = %s AND conversation_id = %s",
                        (row[0], row[1]),
                    ).fetchone()
                    if existing is not None and existing["user_id"] != row[2]:
                        raise RuntimeError("target conversation ownership conflicts with SQLite source")
                    connection.execute(
                        """
                        INSERT INTO rag_conversations
                        (tenant_id, conversation_id, user_id, thread_id, summary, updated_at_ms, expires_at_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                            thread_id = EXCLUDED.thread_id,
                            summary = EXCLUDED.summary,
                            updated_at_ms = EXCLUDED.updated_at_ms,
                            expires_at_ms = EXCLUDED.expires_at_ms
                        """,
                        row,
                    )

        checkpoints = list(source.saver.list(None))
        checkpoints.reverse()
        versions_by_checkpoint: dict[tuple[str, str, str], dict[str, Any]] = {}
        latest_source: dict[tuple[str, str], Any] = {}
        for item in checkpoints:
            configurable = item.config["configurable"]
            thread_id = str(configurable["thread_id"])
            namespace = str(configurable.get("checkpoint_ns", ""))
            checkpoint_id = str(configurable["checkpoint_id"])
            parent_config = item.parent_config
            parent_versions: dict[str, Any] = {}
            if parent_config:
                parent_id = str(parent_config["configurable"]["checkpoint_id"])
                parent_versions = versions_by_checkpoint.get((thread_id, namespace, parent_id), {})
                write_config = parent_config
            else:
                write_config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": namespace}}
            current_versions = dict(item.checkpoint.get("channel_versions") or {})
            new_versions = {
                channel: version
                for channel, version in current_versions.items()
                if parent_versions.get(channel) != version
            }
            target.saver.put(write_config, item.checkpoint, item.metadata, new_versions)
            grouped_writes: dict[str, list[tuple[str, Any]]] = defaultdict(list)
            for task_id, channel, value in item.pending_writes or []:
                grouped_writes[str(task_id)].append((str(channel), value))
            for task_id, writes in grouped_writes.items():
                target.saver.put_writes(item.config, writes, task_id)
            versions_by_checkpoint[(thread_id, namespace, checkpoint_id)] = current_versions
            latest_source[(thread_id, namespace)] = item

        target_items = list(target.saver.list(None))
        latest_target: dict[tuple[str, str], Any] = {}
        for item in target_items:
            configurable = item.config["configurable"]
            key = (str(configurable["thread_id"]), str(configurable.get("checkpoint_ns", "")))
            latest_target.setdefault(key, item)
        for key, source_item in latest_source.items():
            target_item = latest_target.get(key)
            source_id = str(source_item.config["configurable"]["checkpoint_id"])
            target_id = (
                str(target_item.config["configurable"]["checkpoint_id"])
                if target_item is not None
                else None
            )
            if target_id != source_id or target_item.checkpoint.get("channel_values") != source_item.checkpoint.get(
                "channel_values"
            ):
                raise RuntimeError("latest checkpoint semantic verification failed after migration")

        with target.resource.connection() as connection:
            target_conversations = int(
                connection.execute("SELECT COUNT(*) AS count FROM rag_conversations").fetchone()["count"]
            )
        if target_conversations < inventory["conversations"] or len(target_items) < inventory["checkpoints"]:
            raise RuntimeError("target row counts are smaller than the SQLite source")
        source_keys = set(latest_source)
        migrated_pending_writes = sum(
            len(item.pending_writes or [])
            for item in target_items
            if (
                str(item.config["configurable"]["thread_id"]),
                str(item.config["configurable"].get("checkpoint_ns", "")),
            )
            in source_keys
        )
        if migrated_pending_writes != inventory["pending_writes"]:
            raise RuntimeError("pending checkpoint write count differs after migration")
        with target.resource.connection() as connection, connection.transaction():
            connection.execute(
                """
                UPDATE rag_state_migration_runs
                SET status = 'complete', details = %s::jsonb, completed_at = NOW()
                WHERE migration_id = %s
                """,
                (
                    json.dumps(
                        {**inventory, "verified_latest_threads": len(latest_source)},
                        sort_keys=True,
                    ),
                    migration_id,
                ),
            )
        return {
            "mode": "execute",
            **inventory,
            "migration_id": migration_id,
            "verified_latest_threads": len(latest_source),
            "status": "complete",
        }
    except Exception as exc:
        if migration_id is not None:
            try:
                with target.resource.connection() as connection, connection.transaction():
                    connection.execute(
                        """
                        UPDATE rag_state_migration_runs
                        SET status = 'failed', details = %s::jsonb, completed_at = NOW()
                        WHERE migration_id = %s
                        """,
                        (
                            json.dumps(
                                {**inventory, "error_type": type(exc).__name__},
                                sort_keys=True,
                            ),
                            migration_id,
                        ),
                    )
            except Exception:
                pass
        raise
    finally:
        source.close()
        target.close()


def prune_expired_state(settings: Settings) -> dict[str, Any]:
    checkpoints = create_checkpointer(settings)
    try:
        if settings.state_backend == "sqlite":
            conversations = ConversationStore(settings.checkpoint_path)
            coordinator = None
        else:
            from rag_service.coordination import create_coordination

            conversations = PostgresConversationStore(checkpoints.resource)
            coordinator, _quota = create_coordination(settings)
        try:
            if coordinator is None:
                count = conversations.prune_expired(checkpoints.saver)
            else:
                with coordinator.slot("__rag_expired_state_maintenance__"):
                    count = conversations.prune_expired(checkpoints.saver)
            return {"status": "complete", "deleted_conversations": count}
        finally:
            conversations.close()
            if coordinator is not None:
                coordinator.close()
    finally:
        checkpoints.close()


def reconcile_request_runs(settings: Settings) -> dict[str, Any]:
    if settings.state_backend != "postgres":
        raise ValueError("run reconciliation requires RAG_STATE_BACKEND=postgres")
    checkpoints = create_checkpointer(settings)
    try:
        runs = PostgresRequestRunStore(checkpoints.resource)
        reconciled = runs.reconcile_expired()
        return {"status": "complete", "reconciled_runs": reconciled}
    finally:
        checkpoints.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate and maintain RAG service state")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("schema", "sqlite-to-postgres", "prune", "reconcile-runs"),
        default="schema",
    )
    parser.add_argument("--checkpoint-path", default=None)
    parser.add_argument("--sqlite-path", default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "schema":
        if settings.state_backend == "sqlite":
            result = migrate_local_state(args.checkpoint_path or settings.checkpoint_path)
        else:
            result = migrate_postgres_state(settings)
    elif args.command == "prune":
        result = prune_expired_state(settings)
    elif args.command == "reconcile-runs":
        result = reconcile_request_runs(settings)
    else:
        if not args.sqlite_path:
            parser.error("--sqlite-path is required for sqlite-to-postgres")
        if args.execute:
            result = migrate_sqlite_to_postgres(args.sqlite_path, settings)
        else:
            result = inspect_sqlite_state(args.sqlite_path)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
