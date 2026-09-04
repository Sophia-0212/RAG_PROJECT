from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

from langchain_core.documents import Document

from documents.governance import DocumentStatus, GovernanceError, SourceDocument


class OperationKind(str, Enum):
    UPSERT = "upsert"
    DELETE = "delete"


@dataclass(frozen=True)
class ManifestEntry:
    document_id: str
    version_id: str
    content_hash: str
    chunk_ids: tuple[str, ...]
    status: DocumentStatus = DocumentStatus.ACTIVE


@dataclass(frozen=True)
class IngestionManifest:
    tenant_id: str
    generation: int = 0
    entries: Mapping[str, ManifestEntry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise GovernanceError("manifest tenant_id must not be empty")
        if self.generation < 0:
            raise GovernanceError("manifest generation must not be negative")


@dataclass(frozen=True)
class IngestionOperation:
    operation_id: str
    kind: OperationKind
    document_id: str
    version_id: str
    chunk_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class IngestionPlan:
    run_id: str
    plan_id: str
    operations: tuple[IngestionOperation, ...]
    unchanged_document_ids: tuple[str, ...]
    next_manifest: IngestionManifest


def _operation(
    kind: OperationKind,
    document_id: str,
    version_id: str,
    chunk_ids: Sequence[str],
    reason: str,
) -> IngestionOperation:
    normalized_chunk_ids = tuple(sorted(set(chunk_ids)))
    payload = [kind.value, document_id, version_id, normalized_chunk_ids, reason]
    operation_id = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return IngestionOperation(
        operation_id=operation_id,
        kind=kind,
        document_id=document_id,
        version_id=version_id,
        chunk_ids=normalized_chunk_ids,
        reason=reason,
    )


def _manifest_entry(source: SourceDocument, chunks: Sequence[Document]) -> ManifestEntry:
    chunk_ids = tuple(chunk.metadata.get("chunk_id", "") for chunk in chunks)
    if not chunk_ids or any(not chunk_id for chunk_id in chunk_ids):
        raise GovernanceError(f"Governed chunks are required for document {source.document_id}")
    if any(chunk.metadata.get("version_id") != source.version_id for chunk in chunks):
        raise GovernanceError(f"Chunk version mismatch for document {source.document_id}")
    return ManifestEntry(
        document_id=source.document_id,
        version_id=source.version_id,
        content_hash=source.content_hash,
        chunk_ids=tuple(sorted(set(chunk_ids))),
        status=source.status,
    )


def _plan_digest(run_id: str, operations: Iterable[IngestionOperation]) -> str:
    payload = [run_id, [asdict(operation) for operation in operations]]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def plan_ingestion(
    *,
    run_id: str,
    current: IngestionManifest,
    incoming: Sequence[tuple[SourceDocument, Sequence[Document]]],
    authoritative_snapshot: bool = True,
) -> IngestionPlan:
    if not run_id.strip():
        raise GovernanceError("run_id must not be empty")

    incoming_by_id: dict[str, tuple[SourceDocument, Sequence[Document]]] = {}
    for source, chunks in incoming:
        if source.tenant_id != current.tenant_id:
            raise GovernanceError("incoming source tenant does not match the manifest tenant")
        if source.document_id in incoming_by_id:
            raise GovernanceError(f"duplicate incoming document_id: {source.document_id}")
        incoming_by_id[source.document_id] = (source, chunks)

    next_entries = dict(current.entries)
    operations: list[IngestionOperation] = []
    unchanged: list[str] = []

    for document_id in sorted(incoming_by_id):
        source, chunks = incoming_by_id[document_id]
        previous = current.entries.get(document_id)
        if source.status is DocumentStatus.DELETED:
            if previous and previous.status is DocumentStatus.ACTIVE:
                operations.append(
                    _operation(OperationKind.DELETE, document_id, previous.version_id, previous.chunk_ids, "explicit-delete")
                )
            next_entries[document_id] = ManifestEntry(
                document_id=document_id,
                version_id=source.version_id,
                content_hash=source.content_hash,
                chunk_ids=(),
                status=DocumentStatus.DELETED,
            )
            continue

        proposed = _manifest_entry(source, chunks)
        if previous and previous.version_id == proposed.version_id and previous.status is DocumentStatus.ACTIVE:
            unchanged.append(document_id)
            next_entries[document_id] = previous
            continue

        operations.append(
            _operation(OperationKind.UPSERT, document_id, proposed.version_id, proposed.chunk_ids, "new-version")
        )
        if previous and previous.chunk_ids:
            operations.append(
                _operation(OperationKind.DELETE, document_id, previous.version_id, previous.chunk_ids, "superseded-version")
            )
        next_entries[document_id] = proposed

    if authoritative_snapshot:
        missing_ids = sorted(set(current.entries) - set(incoming_by_id))
        for document_id in missing_ids:
            previous = current.entries[document_id]
            if previous.status is DocumentStatus.ACTIVE:
                operations.append(
                    _operation(OperationKind.DELETE, document_id, previous.version_id, previous.chunk_ids, "missing-from-snapshot")
                )
                next_entries[document_id] = ManifestEntry(
                    document_id=document_id,
                    version_id=previous.version_id,
                    content_hash=previous.content_hash,
                    chunk_ids=(),
                    status=DocumentStatus.DELETED,
                )

    operation_tuple = tuple(operations)
    return IngestionPlan(
        run_id=run_id.strip(),
        plan_id=_plan_digest(run_id.strip(), operation_tuple),
        operations=operation_tuple,
        unchanged_document_ids=tuple(sorted(unchanged)),
        next_manifest=IngestionManifest(
            tenant_id=current.tenant_id,
            generation=current.generation + 1,
            entries=next_entries,
        ),
    )
