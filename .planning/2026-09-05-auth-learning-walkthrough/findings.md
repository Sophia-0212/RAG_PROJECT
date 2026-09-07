# Findings & Decisions

## Requirements
- User is a beginner with some AI Agent fundamentals and wants project-level context, not a shallow syntax translation.
- Deliver a learning roadmap that says which method/type to read first.
- Explain auth.py line by line, progressively, with intuition-building examples.
- Do not change business source code.

## Research Findings
- auth.py is 150 lines and uses only Python standard-library modules.
- The file contains two distinct paths: ordinary inbound-request identity verification and recovery-time authorization refresh.
- Shared successful output is immutable IdentityClaims: tenant_id, user_id, normalized principal_ids, and optional policy_version.
- Ordinary authentication is abstracted by IdentityProvider.verify(); recovery refresh is abstracted by RecoveryIdentityResolver.resolve().
- TrustedHeaderIdentityProvider trusts identity headers only when explicitly enabled; GatewaySharedSecretIdentityProvider first authenticates the gateway bearer secret.
- HttpRecoveryIdentityResolver posts tenant/user/request identity to an IAM endpoint and validates both allow/deny and response identity consistency.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Follow actual data flow and call sites before teaching source order | This reveals why each class exists and prevents protocol/dataclass syntax from feeling arbitrary. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- rag_service/auth.py
