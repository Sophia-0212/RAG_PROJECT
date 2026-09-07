from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.schema import CATEGORIES, DatasetError, EvalCase, load_dataset


@dataclass(frozen=True)
class AssetReport:
    dataset_version: str
    snapshot_id: str
    case_count: int
    category_counts: dict[str, int]
    split_counts: dict[str, int]
    evidence_refs_used: int


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_assets(dataset_path: str | Path, manifest_path: str | Path) -> AssetReport:
    cases = load_dataset(dataset_path)
    manifest_file = Path(manifest_path)
    with manifest_file.open("r", encoding="utf-8") as handle:
        manifest: Any = json.load(handle)
    if not isinstance(manifest, dict) or manifest.get("fictional") is not True:
        raise DatasetError("Corpus manifest must declare fictional=true")
    snapshot_id = manifest.get("snapshot_id")
    documents = manifest.get("documents")
    if not isinstance(snapshot_id, str) or not snapshot_id or not isinstance(documents, list):
        raise DatasetError("Corpus manifest needs snapshot_id and documents")

    refs: dict[str, dict[str, Any]] = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            raise DatasetError(f"documents[{index}] must be an object")
        required = ("source_id", "version_id", "path", "effective_from", "acl", "sections")
        if any(field not in document for field in required):
            raise DatasetError(f"documents[{index}] is missing required metadata")
        source_path = manifest_file.parent / str(document["path"])
        if not source_path.is_file():
            raise DatasetError(f"Corpus document does not exist: {source_path}")
        source_text = source_path.read_text(encoding="utf-8")
        for section in document["sections"]:
            if f"## {section}" not in source_text:
                raise DatasetError(f"Corpus section is missing from {source_path}: {section}")
            key = f"{document['source_id']}@{document['version_id']}#{section}"
            if key in refs:
                raise DatasetError(f"Duplicate corpus evidence reference: {key}")
            refs[key] = document

    used_refs: set[str] = set()
    for case in cases:
        if case.annotation.status != "adjudicated":
            raise DatasetError(f"Released case is not adjudicated: {case.case_id}")
        for source in case.relevant_sources:
            used_refs.add(source.key)
            document = refs.get(source.key)
            if document is None:
                raise DatasetError(f"Unknown evidence reference in {case.case_id}: {source.key}")
            as_of = _timestamp(case.as_of)
            if as_of < _timestamp(document["effective_from"]):
                raise DatasetError(f"Evidence is not effective yet in {case.case_id}: {source.key}")
            effective_to = document.get("effective_to")
            if effective_to and as_of > _timestamp(effective_to):
                raise DatasetError(f"Evidence has expired in {case.case_id}: {source.key}")
            if not set(case.principal_ids) & set(document["acl"]):
                raise DatasetError(f"Answer evidence is not authorized in {case.case_id}: {source.key}")
        for ref in case.forbidden_source_refs:
            used_refs.add(ref)
            if ref not in refs:
                raise DatasetError(f"Unknown forbidden evidence in {case.case_id}: {ref}")

    category_counts = Counter(case.category for case in cases)
    split_counts = Counter(case.split for case in cases)
    if set(category_counts) != CATEGORIES or any(category_counts[name] < 3 for name in CATEGORIES):
        raise DatasetError(f"Released dataset does not cover every required category: {dict(category_counts)}")
    if set(split_counts) != {"development", "locked", "security"}:
        raise DatasetError(f"Released dataset must contain all governed splits: {dict(split_counts)}")

    return AssetReport(
        dataset_version=cases[0].dataset_version,
        snapshot_id=snapshot_id,
        case_count=len(cases),
        category_counts=dict(sorted(category_counts.items())),
        split_counts=dict(sorted(split_counts.items())),
        evidence_refs_used=len(used_refs),
    )
