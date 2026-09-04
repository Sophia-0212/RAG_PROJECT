from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from langchain_core.documents import Document

from documents.checkpoint import IngestionCheckpoint, JsonCheckpointStore
from documents.ingestion_plan import IngestionPlan, OperationKind


class IngestionSink(Protocol):
    def upsert(self, documents: Sequence[Document]) -> None: ...

    def delete(self, chunk_ids: Sequence[str]) -> None: ...


class IngestionExecutionError(RuntimeError):
    """Raised after a failed operation has been persisted to the checkpoint."""


def execute_ingestion(
    plan: IngestionPlan,
    chunks_by_version: Mapping[str, Sequence[Document]],
    sink: IngestionSink,
    checkpoint_store: JsonCheckpointStore,
) -> IngestionCheckpoint:
    checkpoint = checkpoint_store.start(plan.run_id, plan.plan_id)
    completed = set(checkpoint.completed_operation_ids)

    for operation in plan.operations:
        if operation.operation_id in completed:
            continue
        try:
            if operation.kind is OperationKind.UPSERT:
                documents = tuple(chunks_by_version.get(operation.version_id, ()))
                actual_chunk_ids = {document.metadata.get("chunk_id") for document in documents}
                if actual_chunk_ids != set(operation.chunk_ids):
                    raise IngestionExecutionError(
                        f"upsert payload does not match operation {operation.operation_id}"
                    )
                sink.upsert(documents)
            else:
                sink.delete(operation.chunk_ids)
            checkpoint = checkpoint_store.mark_completed(checkpoint, operation.operation_id)
            completed.add(operation.operation_id)
        except Exception as exc:
            checkpoint_store.mark_failed(checkpoint, operation.operation_id, str(exc))
            if isinstance(exc, IngestionExecutionError):
                raise
            raise IngestionExecutionError(
                f"ingestion operation {operation.operation_id} failed"
            ) from exc
    return checkpoint
