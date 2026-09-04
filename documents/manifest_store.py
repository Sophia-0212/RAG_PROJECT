from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from documents.governance import DocumentStatus
from documents.ingestion_plan import IngestionManifest, ManifestEntry


class JsonManifestStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self, tenant_id: str) -> IngestionManifest:
        if not self.path.exists():
            return IngestionManifest(tenant_id=tenant_id)
        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if raw.get("tenant_id") != tenant_id:
            raise ValueError("manifest tenant does not match the requested tenant")
        entries = {
            document_id: ManifestEntry(
                document_id=document_id,
                version_id=value["version_id"],
                content_hash=value["content_hash"],
                chunk_ids=tuple(value.get("chunk_ids", ())),
                status=DocumentStatus(value["status"]),
            )
            for document_id, value in raw.get("entries", {}).items()
        }
        return IngestionManifest(
            tenant_id=tenant_id,
            generation=int(raw.get("generation", 0)),
            entries=entries,
        )

    def save(self, manifest: IngestionManifest) -> None:
        payload = {
            "schema_version": 1,
            "tenant_id": manifest.tenant_id,
            "generation": manifest.generation,
            "entries": {
                document_id: {
                    "version_id": entry.version_id,
                    "content_hash": entry.content_hash,
                    "chunk_ids": list(entry.chunk_ids),
                    "status": entry.status.value,
                }
                for document_id, entry in sorted(manifest.entries.items())
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise
