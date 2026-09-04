from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping


class CheckpointError(ValueError):
    """Raised when checkpoint state cannot be safely resumed."""


@dataclass(frozen=True)
class IngestionCheckpoint:
    run_id: str
    plan_id: str
    completed_operation_ids: tuple[str, ...] = ()
    failures: Mapping[str, str] = field(default_factory=dict)

    def remaining(self, operation_ids: tuple[str, ...]) -> tuple[str, ...]:
        completed = set(self.completed_operation_ids)
        return tuple(operation_id for operation_id in operation_ids if operation_id not in completed)


class JsonCheckpointStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> IngestionCheckpoint | None:
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return IngestionCheckpoint(
            run_id=raw["run_id"],
            plan_id=raw["plan_id"],
            completed_operation_ids=tuple(raw.get("completed_operation_ids", ())),
            failures=dict(raw.get("failures", {})),
        )

    def start(self, run_id: str, plan_id: str) -> IngestionCheckpoint:
        current = self.load()
        if current is not None:
            if current.run_id != run_id or current.plan_id != plan_id:
                raise CheckpointError("checkpoint belongs to a different ingestion plan")
            return current
        checkpoint = IngestionCheckpoint(run_id=run_id, plan_id=plan_id)
        self.save(checkpoint)
        return checkpoint

    def mark_completed(self, checkpoint: IngestionCheckpoint, operation_id: str) -> IngestionCheckpoint:
        completed = set(checkpoint.completed_operation_ids)
        completed.add(operation_id)
        failures = dict(checkpoint.failures)
        failures.pop(operation_id, None)
        updated = IngestionCheckpoint(
            run_id=checkpoint.run_id,
            plan_id=checkpoint.plan_id,
            completed_operation_ids=tuple(sorted(completed)),
            failures=failures,
        )
        self.save(updated)
        return updated

    def mark_failed(
        self,
        checkpoint: IngestionCheckpoint,
        operation_id: str,
        reason: str,
    ) -> IngestionCheckpoint:
        failures = dict(checkpoint.failures)
        failures[operation_id] = reason
        updated = IngestionCheckpoint(
            run_id=checkpoint.run_id,
            plan_id=checkpoint.plan_id,
            completed_operation_ids=checkpoint.completed_operation_ids,
            failures=failures,
        )
        self.save(updated)
        return updated

    def save(self, checkpoint: IngestionCheckpoint) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(asdict(checkpoint), handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise
