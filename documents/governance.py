from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Sequence

from langchain_core.documents import Document


GOVERNANCE_SCHEMA_VERSION = 1


class GovernanceError(ValueError):
    """Raised when governed knowledge metadata is invalid."""


class DocumentStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


class Visibility(str, Enum):
    PUBLIC = "public"
    RESTRICTED = "restricted"


def _stable_hash(namespace: str, *parts: Any) -> str:
    payload = json.dumps(
        [namespace, *parts],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_values(values: Iterable[str]) -> tuple[str, ...]:
    normalized = {value.strip() for value in values if value and value.strip()}
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class SourceDocument:
    tenant_id: str
    source_uri: str
    content: str
    title: str = ""
    acl_principals: tuple[str, ...] = ()
    visibility: Visibility = Visibility.RESTRICTED
    status: DocumentStatus = DocumentStatus.ACTIVE
    effective_from_ms: int = 0
    effective_to_ms: int = 0

    def __post_init__(self) -> None:
        tenant_id = self.tenant_id.strip()
        source_uri = self.source_uri.strip()
        if not tenant_id:
            raise GovernanceError("tenant_id must not be empty")
        if not source_uri:
            raise GovernanceError("source_uri must not be empty")
        if self.status is DocumentStatus.ACTIVE and not self.content.strip():
            raise GovernanceError("active source content must not be empty")
        if self.effective_from_ms < 0 or self.effective_to_ms < 0:
            raise GovernanceError("effective timestamps must not be negative")
        if self.effective_to_ms and self.effective_to_ms <= self.effective_from_ms:
            raise GovernanceError("effective_to_ms must be greater than effective_from_ms")

        principals = _normalized_values(self.acl_principals)
        if self.visibility is Visibility.RESTRICTED and not principals:
            raise GovernanceError("restricted sources must declare at least one ACL principal")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "source_uri", source_uri)
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "acl_principals", principals)

    @property
    def source_id(self) -> str:
        return _stable_hash("source", self.tenant_id, self.source_uri)

    @property
    def document_id(self) -> str:
        return _stable_hash("document", self.source_id)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    @property
    def version_id(self) -> str:
        return _stable_hash(
            "version",
            self.document_id,
            self.content_hash,
            self.title,
            self.acl_principals,
            self.visibility.value,
            self.status.value,
            self.effective_from_ms,
            self.effective_to_ms,
            GOVERNANCE_SCHEMA_VERSION,
        )


def govern_chunks(
    source: SourceDocument,
    chunks: Sequence[Document],
    *,
    ingestion_run_id: str,
    chunker_version: str,
) -> list[Document]:
    if source.status is DocumentStatus.DELETED:
        if chunks:
            raise GovernanceError("deleted sources cannot produce active chunks")
        return []
    if not ingestion_run_id.strip():
        raise GovernanceError("ingestion_run_id must not be empty")
    if not chunker_version.strip():
        raise GovernanceError("chunker_version must not be empty")

    prepared = []
    element_to_chunk_id = {}
    for chunk_index, chunk in enumerate(chunks):
        text = chunk.page_content
        if not text.strip():
            continue
        chunk_id = _stable_hash(
            "chunk",
            source.version_id,
            chunker_version,
            chunk_index,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        prepared.append((chunk_index, chunk, chunk_id))
        element_id = chunk.metadata.get("element_id")
        if element_id:
            element_to_chunk_id[str(element_id)] = chunk_id

    governed: list[Document] = []
    for chunk_index, chunk, chunk_id in prepared:
        text = chunk.page_content
        metadata = dict(chunk.metadata)
        metadata.update(
            {
                "governance_schema_version": GOVERNANCE_SCHEMA_VERSION,
                "tenant_id": source.tenant_id,
                "source_uri": source.source_uri,
                "source_id": source.source_id,
                "document_id": source.document_id,
                "version_id": source.version_id,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "content_hash": source.content_hash,
                "status": source.status.value,
                "visibility": source.visibility.value,
                "acl_principals": list(source.acl_principals),
                "effective_from_ms": source.effective_from_ms,
                "effective_to_ms": source.effective_to_ms,
                "ingestion_run_id": ingestion_run_id.strip(),
                "chunker_version": chunker_version.strip(),
            }
        )
        if source.title:
            metadata.setdefault("title", source.title)
        parent_id = chunk.metadata.get("parent_id")
        if parent_id and str(parent_id) in element_to_chunk_id:
            metadata["parent_chunk_id"] = element_to_chunk_id[str(parent_id)]
        governed.append(Document(page_content=text, metadata=metadata))
    return governed
