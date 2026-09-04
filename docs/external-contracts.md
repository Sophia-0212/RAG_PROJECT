# External Service Contracts

## Ownership

The RAG service owns retrieval, evidence authorization, answer generation, citations, bounded retries, and its
conversation checkpoints. It does not own IAM policy evaluation, ONECRM records or writes, Dify workflow state, or
approval execution.

## IAM gateway

Production must inject an `IdentityProvider` that verifies the caller credential and returns tenant, user, principal,
and policy-version claims. The RAG service treats these claims as request scoped and repeats document authorization
after retrieval. Raw identity headers are accepted only in development and test profiles.

## Dify adapter

`POST /integrations/dify/v1/query` accepts `query`, `conversation_id`, and optional `source_ids`/`version_ids` under
`inputs`. It returns the answer plus request ID, citations, refusal reason, and degradation state. Dify owns outer
workflow retries; it should retry only transport or `DEPENDENCY_UNAVAILABLE` failures with the same request ID. A
reason-coded RAG refusal is a completed business response and must not be blindly retried.

## ONECRM and approval services

`CrmActionReference` and `ApprovalReference` are reference schemas only. No RAG endpoint executes CRM mutations or
approval callbacks. A separate action service must reauthorize immediately before execution, apply its own domain
validation, and make `execution_id` idempotent. Approval state, action hashes, compare-and-swap versions, and delayed
resume remain owned by the approval service.

## Error contract

Non-streaming failures use `{ "error": { "code", "message", "request_id" } }`. Streaming failures use an SSE
`error` event with the same fields. Raw prompts, retrieved documents, credentials, stack traces, and checkpoint IDs
must not be included in either contract.
