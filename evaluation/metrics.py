from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence


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


def ndcg_at_k(retrieved_ids: Sequence[str], graded_relevance: Mapping[str, int], k: int) -> float:
    _validate_k(k)
    if not graded_relevance:
        raise ValueError("graded_relevance must not be empty")
    gains = [graded_relevance.get(source_id, 0) for source_id in _unique(retrieved_ids)[:k]]
    dcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal = sorted(graded_relevance.values(), reverse=True)[:k]
    idcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
    return dcg / idcg if idcg else 0.0


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


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)


def fact_coverage(answer: str, acceptable_mentions: Sequence[Sequence[str]]) -> float:
    if not acceptable_mentions:
        raise ValueError("acceptable_mentions must not be empty")
    normalized_answer = normalize_text(answer)
    matched = 0
    for alternatives in acceptable_mentions:
        normalized_alternatives = [normalize_text(item) for item in alternatives if item.strip()]
        if not normalized_alternatives:
            raise ValueError("each fact must include at least one acceptable mention")
        matched += any(phrase in normalized_answer for phrase in normalized_alternatives)
    return matched / len(acceptable_mentions)


def forbidden_fact_rate(answer: str, forbidden_facts: Sequence[str]) -> float:
    if not forbidden_facts:
        return 0.0
    normalized_answer = normalize_text(answer)
    return sum(normalize_text(fact) in normalized_answer for fact in forbidden_facts) / len(forbidden_facts)
