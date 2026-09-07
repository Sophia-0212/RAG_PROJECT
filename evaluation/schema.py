from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class DatasetError(ValueError):
    """Raised when an evaluation dataset violates its contract."""


SPLITS = {"development", "locked", "security"}
CATEGORIES = {
    "single_fact",
    "multi_turn",
    "terminology",
    "multi_hop",
    "temporal_version",
    "ambiguity_no_answer",
    "acl_negative",
    "prompt_injection",
}
RISK_LEVELS = {"low", "medium", "high", "critical"}
ACTIONS = {"answer", "clarify", "refuse"}
ROUTES = {"vectorstore", "direct_answer", "refuse"}


def _required_string(raw: Mapping[str, Any], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise DatasetError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(raw: Mapping[str, Any], field_name: str) -> str | None:
    value = raw.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DatasetError(f"{field_name} must be null or a non-empty string")
    return value.strip()


def _strings(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise DatasetError(f"{field_name} must be a list of non-empty strings")
    normalized = tuple(item.strip() for item in value)
    if len(set(normalized)) != len(normalized):
        raise DatasetError(f"{field_name} must not contain duplicates")
    return normalized


def _objects(value: Any, field_name: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise DatasetError(f"{field_name} must be a list of objects")
    return list(value)


def _choice(value: str, field_name: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise DatasetError(f"Unsupported {field_name}: {value!r}")
    return value


@dataclass(frozen=True)
class EvidenceRef:
    source_id: str
    version_id: str
    section_id: str
    relevance_grade: int = 3
    required: bool = True

    @property
    def key(self) -> str:
        return f"{self.source_id}@{self.version_id}#{self.section_id}"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], field_name: str) -> "EvidenceRef":
        grade = raw.get("relevance_grade", 3)
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in {1, 2, 3}:
            raise DatasetError(f"{field_name}.relevance_grade must be 1, 2, or 3")
        required = raw.get("required", True)
        if not isinstance(required, bool):
            raise DatasetError(f"{field_name}.required must be a boolean")
        return cls(
            source_id=_required_string(raw, "source_id"),
            version_id=_required_string(raw, "version_id"),
            section_id=_required_string(raw, "section_id"),
            relevance_grade=grade,
            required=required,
        )


@dataclass(frozen=True)
class FactExpectation:
    fact_id: str
    statement: str
    evidence_refs: tuple[str, ...]
    match_any: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], field_name: str) -> "FactExpectation":
        return cls(
            fact_id=_required_string(raw, "fact_id"),
            statement=_required_string(raw, "statement"),
            evidence_refs=_strings(raw.get("evidence_refs"), f"{field_name}.evidence_refs"),
            match_any=_strings(raw.get("match_any"), f"{field_name}.match_any"),
        )


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], field_name: str) -> "ConversationTurn":
        role = _choice(_required_string(raw, "role"), f"{field_name}.role", {"user", "assistant"})
        return cls(role=role, content=_required_string(raw, "content"))


@dataclass(frozen=True)
class AnnotationAudit:
    method: str
    status: str
    guideline_version: str
    annotator_roles: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AnnotationAudit":
        method = _choice(
            _required_string(raw, "method"),
            "annotation.method",
            {"synthetic_sme", "sanitized_production", "adversarial"},
        )
        status = _choice(
            _required_string(raw, "status"),
            "annotation.status",
            {"draft", "double_reviewed", "adjudicated"},
        )
        roles = _strings(raw.get("annotator_roles"), "annotation.annotator_roles")
        if not roles:
            raise DatasetError("annotation.annotator_roles must not be empty")
        return cls(
            method=method,
            status=status,
            guideline_version=_required_string(raw, "guideline_version"),
            annotator_roles=roles,
        )


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    dataset_version: str
    split: str
    category: str
    business_domain: str
    risk_level: str
    tenant_id: str
    principal_ids: tuple[str, ...]
    as_of: str
    question: str
    history: tuple[ConversationTurn, ...]
    expected_action: str
    expected_route: str
    relevant_sources: tuple[EvidenceRef, ...]
    required_facts: tuple[FactExpectation, ...]
    forbidden_source_refs: tuple[str, ...]
    forbidden_facts: tuple[str, ...]
    refusal_reason: str | None
    clarification_points: tuple[str, ...]
    tags: tuple[str, ...]
    annotation: AnnotationAudit

    @property
    def expected_source_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(source.source_id for source in self.relevant_sources if source.required))

    @property
    def expected_source_refs(self) -> tuple[str, ...]:
        return tuple(source.key for source in self.relevant_sources if source.required)

    @property
    def graded_source_refs(self) -> dict[str, int]:
        return {source.key: source.relevance_grade for source in self.relevant_sources}

    @property
    def expected_facts(self) -> tuple[str, ...]:
        return tuple(fact.statement for fact in self.required_facts)

    @property
    def forbidden_source_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(ref.split("@", 1)[0] for ref in self.forbidden_source_refs))

    @property
    def should_refuse(self) -> bool:
        return self.expected_action == "refuse"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EvalCase":
        split = _choice(_required_string(raw, "split"), "split", SPLITS)
        category = _choice(_required_string(raw, "category"), "category", CATEGORIES)
        risk_level = _choice(_required_string(raw, "risk_level"), "risk_level", RISK_LEVELS)
        expected_action = _choice(_required_string(raw, "expected_action"), "expected_action", ACTIONS)
        expected_route = _choice(_required_string(raw, "expected_route"), "expected_route", ROUTES)
        as_of = _required_string(raw, "as_of")
        try:
            parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DatasetError("as_of must be an ISO-8601 timestamp") from exc
        if parsed_as_of.tzinfo is None:
            raise DatasetError("as_of must include a timezone")

        relevant_sources = tuple(
            EvidenceRef.from_mapping(item, f"relevant_sources[{index}]")
            for index, item in enumerate(_objects(raw.get("relevant_sources"), "relevant_sources"))
        )
        required_facts = tuple(
            FactExpectation.from_mapping(item, f"required_facts[{index}]")
            for index, item in enumerate(_objects(raw.get("required_facts"), "required_facts"))
        )
        history = tuple(
            ConversationTurn.from_mapping(item, f"history[{index}]")
            for index, item in enumerate(_objects(raw.get("history"), "history"))
        )
        annotation_raw = raw.get("annotation")
        if not isinstance(annotation_raw, Mapping):
            raise DatasetError("annotation must be an object")

        case = cls(
            case_id=_required_string(raw, "case_id"),
            dataset_version=_required_string(raw, "dataset_version"),
            split=split,
            category=category,
            business_domain=_required_string(raw, "business_domain"),
            risk_level=risk_level,
            tenant_id=_required_string(raw, "tenant_id"),
            principal_ids=_strings(raw.get("principal_ids"), "principal_ids"),
            as_of=as_of,
            question=_required_string(raw, "question"),
            history=history,
            expected_action=expected_action,
            expected_route=expected_route,
            relevant_sources=relevant_sources,
            required_facts=required_facts,
            forbidden_source_refs=_strings(raw.get("forbidden_source_refs"), "forbidden_source_refs"),
            forbidden_facts=_strings(raw.get("forbidden_facts"), "forbidden_facts"),
            refusal_reason=_optional_string(raw, "refusal_reason"),
            clarification_points=_strings(raw.get("clarification_points"), "clarification_points"),
            tags=_strings(raw.get("tags"), "tags"),
            annotation=AnnotationAudit.from_mapping(annotation_raw),
        )
        case._validate_contract()
        return case

    def _validate_contract(self) -> None:
        if not self.principal_ids:
            raise DatasetError("principal_ids must not be empty")
        relevant_keys = [source.key for source in self.relevant_sources]
        if len(set(relevant_keys)) != len(relevant_keys):
            raise DatasetError("relevant_sources must not contain duplicate evidence references")
        overlap = set(relevant_keys) & set(self.forbidden_source_refs)
        if overlap:
            raise DatasetError(f"Evidence cannot be both relevant and forbidden: {sorted(overlap)}")

        if self.expected_action == "answer":
            if self.expected_route != "vectorstore":
                raise DatasetError("answer cases must use the vectorstore route")
            if not self.expected_source_refs:
                raise DatasetError("answer cases must declare required relevant_sources")
            if not self.required_facts:
                raise DatasetError("answer cases must declare required_facts")
        elif self.expected_action == "clarify":
            if self.expected_route != "direct_answer" or not self.clarification_points:
                raise DatasetError("clarify cases require direct_answer and clarification_points")
        elif self.expected_action == "refuse":
            if self.expected_route != "refuse" or not self.refusal_reason:
                raise DatasetError("refuse cases require the refuse route and refusal_reason")

        allowed_evidence = set(relevant_keys)
        for fact in self.required_facts:
            if not fact.evidence_refs or not fact.match_any:
                raise DatasetError(f"Fact {fact.fact_id!r} needs evidence_refs and match_any")
            missing = set(fact.evidence_refs) - allowed_evidence
            if missing:
                raise DatasetError(f"Fact {fact.fact_id!r} cites undeclared evidence: {sorted(missing)}")

        if self.category == "multi_turn" and not self.history:
            raise DatasetError("multi_turn cases must include history")
        if self.category == "acl_negative" and not self.forbidden_source_refs:
            raise DatasetError("acl_negative cases must declare forbidden_source_refs")
        if self.category == "temporal_version" and not self.forbidden_source_refs:
            raise DatasetError("temporal_version cases must declare superseded forbidden_source_refs")


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
            try:
                case = EvalCase.from_mapping(raw)
            except DatasetError as exc:
                raise DatasetError(f"Line {line_number}: {exc}") from exc
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
