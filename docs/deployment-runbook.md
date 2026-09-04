# Deployment and Rollback Runbook

This runbook covers the RAG service container and its local SQLite state. It does not provision Milvus, IAM, the
LLM gateway, Dify, ONECRM, or the approval platform. Those systems must satisfy the contracts in
`docs/external-contracts.md` before rollout.

## Release inputs

Record these immutable values in the change ticket:

- Git commit and built image digest. Deploy by digest, not by a mutable tag.
- Dataset, graph, prompt, embedding, reranker, index, and collection/alias versions.
- Milvus target and the currently active collection behind the serving alias.
- Evaluation-gate output and target-environment load-report path.
- Rollback image digest and previous Milvus collection.

Generate a random gateway secret of at least 32 characters and provide all values required by
`deploy/docker-compose.yml` through the deployment secret store. Do not place them in Git, shell history, image
layers, or support tickets.

The default container is offline for Hugging Face access. Preload the configured reranker into an absolute host
cache directory and set `RAG_MODEL_CACHE_PATH`. If production policy permits model download instead, build a derived
image containing the reviewed model artifact; do not make first-request internet access part of readiness.

## Preflight

1. Confirm the image architecture and digest match the release record.
2. Confirm Milvus is reachable from the service network and does not resolve to localhost.
3. Confirm the gateway validates the caller and replaces, rather than appends, forwarded identity headers.
4. Confirm the checkpoint path is backed by persistent storage with a tested restore procedure.
5. Confirm the reranker cache is readable by UID/GID `10001` and contains the reviewed model revision.
6. Run the offline suite, dependency audit, image vulnerability scan, and repository secret scan from CI.
7. Run `rag-eval-gate` on the release metrics. A failed required rule blocks promotion.

Validate the composed deployment without printing real secrets:

```bash
OPENAI_API_KEY=preflight-only \
RAG_GATEWAY_SHARED_SECRET=preflight-only-secret-at-least-32-characters \
MILVUS_URI=https://milvus.internal:19530 \
RAG_COLLECTION_NAME=rag_active \
RAG_LLM_BASE_URL=https://llm-gateway.internal/v1 \
RAG_MODEL_CACHE_PATH=/absolute/path/to/reviewed-model-cache \
docker compose -f deploy/docker-compose.yml config --quiet
```

## State migration

Back up the persistent volume before migrating. The current migration creates or upgrades LangGraph checkpoint and
conversation tables idempotently and prunes expired conversations:

```bash
docker compose -f deploy/docker-compose.yml run --rm rag-service \
  python -m rag_service.migrations --checkpoint-path /var/lib/rag/checkpoints.sqlite3
```

Run the same command twice in staging; both runs must report `checkpoint` and `conversation` as `ready`. Restore the
backup and previous image if migration verification fails.

SQLite supports one service process only. Do not increase Uvicorn workers or replicas. Multi-instance rollout is
blocked until a shared production checkpointer, distributed conversation expiry, and their migration tests exist.

## Index promotion

Build a versioned collection with governed ingestion. Do not overwrite the serving collection. Validate row counts,
required governed metadata, tenant/ACL negative cases, retrieval metrics, and citation integrity before switching the
alias. Record the observed old collection and use the guarded alias operation so a stale release cannot replace a
newer one.

## Rollout

1. Deploy one instance with the new image digest and persistent state mounted.
2. Wait for `/health/live` and `/health/ready` to return HTTP 200.
3. Send an authenticated canary query for an allowed document, a forbidden document, and a missing-evidence case.
4. Confirm request IDs correlate with redacted events and Prometheus metrics without raw question or document text.
5. Run a small load probe, then the approved load profile. Compare only like-for-like component versions.
6. Observe dependency errors, degraded rerank rate, refusal reasons, latency, quota rejection, and resource use for the
   agreed soak period before completing promotion.

## Rollback

Rollback triggers include cross-tenant exposure, incorrect authorization, corrupt citations, migration failure,
unbounded retry behavior, sustained dependency saturation, or a failed release gate.

1. Stop new traffic at the gateway.
2. Roll the service back to the recorded image digest.
3. If the index changed, switch the alias back using the recorded expected-current collection guard.
4. Restore the checkpoint backup only when the schema/data migration caused the incident. Do not overwrite healthy
   newer conversations for an application-only rollback.
5. Re-run readiness and the three canary cases before reopening traffic.
6. Preserve metrics, redacted events, release metadata, and migration output for the incident record.

