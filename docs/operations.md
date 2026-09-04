# Operations and Degradation

## Signals

Prometheus metrics are exposed at `/metrics`. Metric labels are restricted to bounded outcome, reason, degraded, and
action values; tenant, user, request, conversation, document, and model identifiers are not labels. Structured events
carry request correlation and hashed identity plus candidate/citation lineage, but never raw question, prompt,
document, credential, or conversation-summary text.

Exact provider token and cost data is not yet available from every configured gateway. `estimated_tokens` is a
conservative local budget counter, not a billing metric.

## Failure matrix

| Failure | Behavior | Contract |
| --- | --- | --- |
| Tenant quota exhausted | Reject before Graph execution | HTTP 429 `TENANT_QUOTA_EXCEEDED` |
| Global concurrency full | Wait briefly, then reject | HTTP 503 `SERVICE_BUSY` |
| Retrieval/Web/LLM transient failure | Bounded retry with jitter; circuit records final failure | HTTP 503 `DEPENDENCY_UNAVAILABLE` |
| Dependency circuit open | Fail fast without consuming downstream capacity | HTTP 503 `DEPENDENCY_UNAVAILABLE` |
| Reranker timeout/error/open circuit | Preserve authorized recall order | Answer has `degraded=true` and a reason in Graph state |
| Graph budget/deadline/no progress | Stop at the common terminal node | Completed refusal with stable reason code |
| Streaming client disconnect | Stop consuming the graph iterator and release local locks/capacity | Connection closes; no synthetic success |
| SQLite metadata/checkpoint failure | Do not continue with untracked state | HTTP 500 `INTERNAL_ERROR` |

Retries are confined to idempotent reads and model inference. The service does not retry CRM actions, approval
callbacks, or a complete workflow invocation.

## Performance evidence

Run `python -m evaluation.load_test` against the intended environment and retain its JSON output with the application,
model, prompt, graph, index, embedding, and reranker versions. Compare reports only when those versions and the dataset
are known. The repository intentionally contains no copied throughput or percentile claim from the simulated project.
