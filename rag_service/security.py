from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from langchain_core.documents import Document


class SecurityContextError(ValueError):
    """Raised when a request cannot be authorized safely."""


def _normalized(values: Sequence[str], field_name: str, limit: int = 100) -> tuple[str, ...]:
    normalized = tuple(sorted({value.strip() for value in values if value and value.strip()}))
    if len(normalized) > limit:
        raise SecurityContextError(f"{field_name} exceeds the maximum of {limit} values")
    return normalized


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    tenant_id: str
    user_id: str
    principal_ids: tuple[str, ...] = ()
    now_ms: int = 0

    def __post_init__(self) -> None:
        request_id = self.request_id.strip()
        tenant_id = self.tenant_id.strip()
        user_id = self.user_id.strip()
        if not request_id or not tenant_id or not user_id:
            raise SecurityContextError("request_id, tenant_id, and user_id are required")
        principals = set(_normalized(self.principal_ids, "principal_ids"))
        principals.add(f"user:{user_id}")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "principal_ids", tuple(sorted(principals)))
        object.__setattr__(self, "now_ms", self.now_ms or int(time.time() * 1000))

    @classmethod
    def from_value(cls, value: "RequestContext | Mapping[str, Any]") -> "RequestContext":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise SecurityContextError("request_context is required")
        return cls(
            request_id=str(value.get("request_id", "")),
            tenant_id=str(value.get("tenant_id", "")),
            user_id=str(value.get("user_id", "")),
            principal_ids=tuple(value.get("principal_ids", ())),
            now_ms=int(value.get("now_ms", 0)),
        )


@dataclass(frozen=True)
class QueryConstraints:
    source_ids: tuple[str, ...] = ()
    version_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ids", _normalized(self.source_ids, "source_ids"))
        object.__setattr__(self, "version_ids", _normalized(self.version_ids, "version_ids"))

    @classmethod
    def from_value(cls, value: "QueryConstraints | Mapping[str, Any] | None") -> "QueryConstraints":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise SecurityContextError("query_constraints must be an object")
        return cls(
            source_ids=tuple(value.get("source_ids", ())),
            version_ids=tuple(value.get("version_ids", ())),
        )


def _literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _string_list(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def build_milvus_filter(context: RequestContext, constraints: QueryConstraints | None = None) -> str:
    constraints = constraints or QueryConstraints()
    clauses = [
        f"tenant_id == {_literal(context.tenant_id)}",
        'status == "active"',
        '(category == "content" or category == "NarrativeText")',
        f"(effective_from_ms == 0 or effective_from_ms <= {context.now_ms})",
        f"(effective_to_ms == 0 or effective_to_ms > {context.now_ms})",
    ]
    authorization = 'visibility == "public"'
    if context.principal_ids:
        authorization += f" or json_contains_any(acl_principals, {_string_list(context.principal_ids)})"
    clauses.append(f"({authorization})")
    if constraints.source_ids:
        clauses.append(f"source_id in {_string_list(constraints.source_ids)}")
    if constraints.version_ids:
        clauses.append(f"version_id in {_string_list(constraints.version_ids)}")
    return " and ".join(f"({clause})" for clause in clauses)


def is_document_authorized(document: Document, context: RequestContext) -> bool:
    metadata = document.metadata
    if metadata.get("tenant_id") != context.tenant_id:
        return False
    if metadata.get("status") != "active":
        return False
    effective_from = metadata.get("effective_from_ms")
    effective_to = metadata.get("effective_to_ms")
    if not isinstance(effective_from, int) or not isinstance(effective_to, int):
        return False
    if effective_from and effective_from > context.now_ms:
        return False
    if effective_to and effective_to <= context.now_ms:
        return False
    visibility = metadata.get("visibility")
    if visibility == "public":
        return True
    if visibility != "restricted":
        return False
    acl_principals = metadata.get("acl_principals")
    if not isinstance(acl_principals, list):
        return False
    return bool(set(context.principal_ids) & set(acl_principals))
