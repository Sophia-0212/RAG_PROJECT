from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Protocol, Sequence


class AuthenticationError(PermissionError):
    """Raised when identity headers cannot be trusted or validated."""


@dataclass(frozen=True)
class IdentityClaims:
    tenant_id: str
    user_id: str
    principal_ids: tuple[str, ...]
    policy_version: str = ""


class IdentityProvider(Protocol):
    def verify(
        self,
        *,
        tenant_id: str | None,
        user_id: str | None,
        principal_ids: Sequence[str],
        authorization: str | None,
    ) -> IdentityClaims: ...


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
