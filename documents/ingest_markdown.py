from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from uuid import uuid4

from documents.checkpoint import JsonCheckpointStore
from documents.governance import Visibility
from documents.ingestion_plan import IngestionManifest, plan_ingestion
from documents.ingestion_runner import execute_ingestion
from documents.manifest_store import JsonManifestStore
from documents.markdown_parser import MarkdownParser
from documents.milvus_db import MilvusIngestionSink, MilvusVectorSave
from documents.source_adapter import MarkdownSourceAdapter
from rag_service.settings import get_settings


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    if not normalized:
        raise ValueError("state path segment must not be empty")
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed, resumable Markdown ingestion")
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--acl", action="append", default=[], help="Allowed principal; repeat as needed")
    parser.add_argument("--public", action="store_true", help="Mark source documents public")
    parser.add_argument("--run-id", default=None, help="Stable ID required to resume an interrupted run")
    parser.add_argument("--chunker-version", default="markdown-v1")
    parser.add_argument("--state-dir", type=Path, default=Path(".rag-state"))
    parser.add_argument("--collection-version", default=None, help="Build a full versioned collection")
    parser.add_argument("--activate-alias", default=None, help="Activate this alias after a successful build")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    visibility = Visibility.PUBLIC if args.public else Visibility.RESTRICTED
    if visibility is Visibility.RESTRICTED and not args.acl:
        raise SystemExit("At least one --acl is required unless --public is set")

    settings = get_settings()
    run_id = args.run_id or str(uuid4())
    tenant_segment = _safe_segment(args.tenant)
    adapter = MarkdownSourceAdapter(
        root=args.source_dir,
        tenant_id=args.tenant,
        acl_principals=tuple(args.acl),
        visibility=visibility,
    )
    parser = MarkdownParser()
    governed_pairs = []
    chunks_by_version = {}
    for path, source in adapter.scan():
        chunks = parser.parse_governed_markdown(
            str(path),
            source,
            ingestion_run_id=run_id,
            chunker_version=args.chunker_version,
        )
        governed_pairs.append((source, chunks))
        chunks_by_version[source.version_id] = chunks

    store = MilvusVectorSave(settings=settings)
    if args.collection_version:
        target_collection = store.create_versioned_collection(args.collection_version)
        current = IngestionManifest(tenant_id=args.tenant)
    else:
        target_collection = settings.collection_name
        store.ensure_collection(target_collection)
        manifest_path = args.state_dir / "manifests" / tenant_segment / f"{target_collection}.json"
        current = JsonManifestStore(manifest_path).load(args.tenant)

    manifest_path = args.state_dir / "manifests" / tenant_segment / f"{target_collection}.json"
    manifest_store = JsonManifestStore(manifest_path)
    plan = plan_ingestion(
        run_id=run_id,
        current=current,
        incoming=governed_pairs,
        authoritative_snapshot=True,
    )

    store.create_connection(target_collection)
    checkpoint_path = args.state_dir / "checkpoints" / tenant_segment / f"{_safe_segment(run_id)}.json"
    checkpoint = execute_ingestion(
        plan,
        chunks_by_version,
        MilvusIngestionSink(store),
        JsonCheckpointStore(checkpoint_path),
    )
    manifest_store.save(plan.next_manifest)

    alias_switch = None
    if args.activate_alias:
        alias_switch = store.activate_alias(args.activate_alias, target_collection)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "plan_id": plan.plan_id,
                "collection": target_collection,
                "operations": len(plan.operations),
                "unchanged_documents": len(plan.unchanged_document_ids),
                "completed_operations": len(checkpoint.completed_operation_ids),
                "alias_previous_collection": (
                    alias_switch.current_collection if alias_switch is not None else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
