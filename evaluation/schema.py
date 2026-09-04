from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DatasetError(ValueError):
    """Raised when an evaluation dataset violates its contract."""


def _strings(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise DatasetError(f"{field_name} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    dataset_version: str
    question: str
    expected_source_ids: tuple[str, ...]
    expected_facts: tuple[str, ...]
    forbidden_source_ids: tuple[str, ...] = ()
    expected_route: str = "vectorstore"
    should_refuse: bool = False
    tags: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EvalCase":
        required = ("case_id", "dataset_version", "question")
        for field_name in required:
            value = raw.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise DatasetError(f"{field_name} must be a non-empty string")

        should_refuse = raw.get("should_refuse", False)
        if not isinstance(should_refuse, bool):
            raise DatasetError("should_refuse must be a boolean")

        expected_route = raw.get("expected_route", "vectorstore")
        if expected_route not in {"vectorstore", "web_search", "direct_answer", "refuse"}:
            raise DatasetError(f"Unsupported expected_route: {expected_route!r}")

        case = cls(
            case_id=raw["case_id"].strip(),
            dataset_version=raw["dataset_version"].strip(),
            question=raw["question"].strip(),
            expected_source_ids=_strings(raw.get("expected_source_ids"), "expected_source_ids"),
            expected_facts=_strings(raw.get("expected_facts"), "expected_facts"),
            forbidden_source_ids=_strings(raw.get("forbidden_source_ids"), "forbidden_source_ids"),
            expected_route=expected_route,
            should_refuse=should_refuse,
            tags=_strings(raw.get("tags"), "tags"),
        )
        if not case.should_refuse and case.expected_route == "vectorstore" and not case.expected_source_ids:
            raise DatasetError("A vectorstore case must declare expected_source_ids")
        overlap = set(case.expected_source_ids) & set(case.forbidden_source_ids)
        if overlap:
            raise DatasetError(f"Sources cannot be both expected and forbidden: {sorted(overlap)}")
        return case


def load_dataset(path: str | Path) -> list[EvalCase]:
    dataset_path = Path(path)
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    versions: set[str] = set()
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"Invalid JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(raw, dict):
                raise DatasetError(f"Line {line_number} must contain a JSON object")
            case = EvalCase.from_mapping(raw)
            if case.case_id in seen_ids:
                raise DatasetError(f"Duplicate case_id: {case.case_id}")
            seen_ids.add(case.case_id)
            versions.add(case.dataset_version)
            cases.append(case)

    if not cases:
        raise DatasetError("Evaluation dataset is empty")
    if len(versions) != 1:
        raise DatasetError(f"A dataset file must contain one version, got: {sorted(versions)}")
    return cases
