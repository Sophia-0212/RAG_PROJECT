from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
from typing import Any, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AuthenticationError(PermissionError):
    """Raised when identity headers cannot be trusted or validated."""


@dataclass(frozen=True)
class IdentityClaims:
    tenant_id: str  # 租户ID：这次请求归属哪个组织/业务线，数据隔离的最外层边界
    user_id: str  # 用户ID：这个租户下具体是谁在操作
    principal_ids: tuple[str, ...]  # 角色/权限标签列表，决定在租户内部这个人具体能看什么、能做什么
    policy_version: str = ""  # 本次身份判定所依据的策略版本号，仅恢复授权流程会真正赋值，用于审计追溯当时用的是哪版规则


class IdentityProvider(Protocol):
    def verify(
        self,
        *,
        tenant_id: str | None,
        user_id: str | None,
        principal_ids: Sequence[str],
        authorization: str | None,
    ) -> IdentityClaims: ...


class RecoveryAuthorizationError(PermissionError):
    """Recovery authorization was denied or could not be refreshed."""


class RecoveryAuthorizationUnavailable(RecoveryAuthorizationError):
    """The authorization service could not provide a fresh decision."""


class RecoveryAuthorizationDenied(RecoveryAuthorizationError):
    """The fresh authorization decision explicitly denied recovery."""


class RecoveryIdentityResolver(Protocol):
    def resolve(self, *, tenant_id: str, user_id: str, request_id: str) -> IdentityClaims: ...


class HttpRecoveryIdentityResolver:
    """Refresh identity/principals through the enterprise IAM recovery contract."""

    def __init__(self, url: str, token: str, *, timeout_seconds: float = 3.0):
        if not url.strip() or not token.strip():
            raise ValueError("recovery authorization URL and token are required")
        self._url = url
        self._token = token
        self._timeout_seconds = timeout_seconds

    def resolve(self, *, tenant_id: str, user_id: str, request_id: str) -> IdentityClaims:
        payload = json.dumps(
            {"tenant_id": tenant_id, "user_id": user_id, "request_id": request_id},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self._url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                document: Any = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise RecoveryAuthorizationDenied("recovery authorization was denied") from exc
            raise RecoveryAuthorizationUnavailable("recovery authorization is unavailable") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise RecoveryAuthorizationUnavailable("recovery authorization is unavailable") from exc
        if not isinstance(document, dict) or document.get("allowed") is not True:
            raise RecoveryAuthorizationDenied("recovery authorization was denied")
        if document.get("tenant_id", tenant_id) != tenant_id or document.get("user_id", user_id) != user_id:
            raise RecoveryAuthorizationDenied("recovery authorization identity mismatch")
        principals = document.get("principal_ids", [])
        if not isinstance(principals, list) or len(principals) > 100:
            raise RecoveryAuthorizationUnavailable("recovery authorization response is invalid")
        normalized = tuple(sorted({str(value).strip() for value in principals if str(value).strip()}))
        return IdentityClaims(
            tenant_id=tenant_id,
            user_id=user_id,
            principal_ids=normalized,
            policy_version=str(document.get("policy_version", "")),
        )


class TrustedHeaderIdentityProvider:
    """Development-only adapter for identity headers set by a trusted gateway."""

    def __init__(self, *, enabled: bool):
        self.enabled = enabled

    def verify(
        self,
        *,
        tenant_id: str | None,
        user_id: str | None,
        principal_ids: Sequence[str],
        authorization: str | None,
    ) -> IdentityClaims:
        if not self.enabled:
            raise AuthenticationError("a production identity provider is not configured")
        tenant = (tenant_id or "").strip()
        user = (user_id or "").strip()
        if not tenant or not user:
            raise AuthenticationError("X-Tenant-ID and X-User-ID are required")
        normalized = tuple(sorted({value.strip() for value in principal_ids if value.strip()}))
        if len(normalized) > 100:
            raise AuthenticationError("too many principals")
        return IdentityClaims(tenant_id=tenant, user_id=user, principal_ids=normalized)


class GatewaySharedSecretIdentityProvider(TrustedHeaderIdentityProvider):
    """Verify a private gateway bearer secret before accepting forwarded identity."""

    def __init__(self, shared_secret: str):
        if len(shared_secret.strip()) < 32:
            raise ValueError("shared_secret must contain at least 32 characters")
        super().__init__(enabled=True)
        self._shared_secret = shared_secret

    def verify(
        self,
        *,
        tenant_id: str | None,
        user_id: str | None,
        principal_ids: Sequence[str],
        authorization: str | None,
    ) -> IdentityClaims:
        scheme, separator, credential = (authorization or "").partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not secrets.compare_digest(
            credential,
            self._shared_secret,
        ):
            raise AuthenticationError("gateway authentication failed")
        return super().verify(
            tenant_id=tenant_id,
            user_id=user_id,
            principal_ids=principal_ids,
            authorization=authorization,
        )
