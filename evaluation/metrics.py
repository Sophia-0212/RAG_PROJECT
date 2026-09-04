from __future__ import annotations

from collections.abc import Iterable, Sequence


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _validate_k(k: int) -> None:
    if k <= 0:
        raise ValueError("k must be greater than zero")


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    _validate_k(k)
    relevant = set(_unique(relevant_ids))
    if not relevant:
        raise ValueError("relevant_ids must not be empty")
    retrieved = set(_unique(retrieved_ids)[:k])
    return len(retrieved & relevant) / len(relevant)


def hit_rate_at_k(retrieved_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    _validate_k(k)
    relevant = set(_unique(relevant_ids))
    if not relevant:
        raise ValueError("relevant_ids must not be empty")
    return float(bool(set(_unique(retrieved_ids)[:k]) & relevant))


def reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: Sequence[str]) -> float:
    relevant = set(_unique(relevant_ids))
    if not relevant:
        raise ValueError("relevant_ids must not be empty")
    for rank, source_id in enumerate(_unique(retrieved_ids), start=1):
        if source_id in relevant:
            return 1.0 / rank
    return 0.0


def citation_precision(cited_ids: Sequence[str], supported_ids: Sequence[str]) -> float:
    cited = set(_unique(cited_ids))
    if not cited:
        return 0.0
    return len(cited & set(_unique(supported_ids))) / len(cited)


def citation_recall(cited_ids: Sequence[str], required_ids: Sequence[str]) -> float:
    required = set(_unique(required_ids))
    if not required:
        raise ValueError("required_ids must not be empty")
    return len(set(_unique(cited_ids)) & required) / len(required)


def leakage_rate(retrieved_ids: Sequence[str], forbidden_ids: Sequence[str]) -> float:
    retrieved = _unique(retrieved_ids)
    if not retrieved:
        return 0.0
    forbidden = set(_unique(forbidden_ids))
    return sum(source_id in forbidden for source_id in retrieved) / len(retrieved)
