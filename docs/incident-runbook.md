# Incident Runbook

## First response

Assign an incident owner, freeze releases, record the first failing request ID and release versions, then decide
whether confidentiality or authorization may be affected. If tenant isolation is uncertain, stop query traffic
immediately. Never paste prompts, retrieved text, credentials, or conversation summaries into the incident channel.

Use `/health/live` for process health, `/health/ready` for local state/auth readiness, and `/metrics` for aggregate
behavior. Correlate an individual request through allowlisted structured events by request ID and hashed tenant ID.

## Triage matrix

| Signal | Checks | Immediate action |
| --- | --- | --- |
| Cross-tenant result or unauthorized citation | Request identity, Milvus filter, candidate lineage, policy/index version | Stop traffic; preserve evidence; roll back image and index alias |
| Increased `DEPENDENCY_UNAVAILABLE` | Milvus/LLM/web breaker state, timeouts, upstream health | Keep retries bounded; shed load; disable optional web route; fail closed |
| Increased degraded answers | Reranker timeout/error/open circuit, model mount and CPU pressure | Keep authorized recall fallback; repair model/runtime; do not bypass ACL |
| Increased refusal/no-progress | Retrieval candidates, context budget, graph counters, index release | Compare component versions; roll back index or graph when correlated |
| HTTP 429 | Tenant rate and burst, caller behavior | Preserve fairness; coordinate a reviewed quota change only after capacity proof |
| HTTP 503 `SERVICE_BUSY` | In-flight gauge, latency, worker/resource saturation | Reduce ingress concurrency; do not add SQLite replicas |
| Readiness failure | Persistent volume, SQLite permissions/schema, identity provider configuration | Remove instance from traffic; restore volume or configuration |
| Latency regression | Action histograms and dependency latency by bounded action label | Isolate the slow dependency; invoke documented fallback/rollback |

## Evidence collection

Retain the image digest, commit, request IDs, UTC time window, component versions, active collection/alias, relevant
metrics snapshot, redacted event records, and load/evaluation reports. Access to these artifacts follows the same
tenant and production-data controls as the service. Do not expand telemetry fields during an incident without a
privacy review.

## Recovery and closure

Recovery requires readiness, allowed/forbidden/missing-evidence canaries, and confirmation that retry and breaker
budgets returned to normal. For authorization incidents, rotate gateway secrets and review index/query logs before
reopening traffic. Close only after the corrective change has an offline regression test and, where applicable, a
staging reproduction. Recalibrate alerts from measured evidence; do not backfill a claimed SLO from this incident.

