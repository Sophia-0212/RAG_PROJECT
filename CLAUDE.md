# RAG_PROJECT Development Guide

`README.md` is the authoritative setup and capability document. This file contains repository-specific rules for coding agents.

## Project direction

- Domain: CRM sales SOP, product behavior, and troubleshooting knowledge.
- Canonical workflow: `graph2`, composed through `rag_service.application.create_graph()`.
- Legacy examples: `graph` and `agent/rag_agent.py`; keep them import-safe, but do not extend them as production paths.
- Retrieval: Milvus dense + BM25 sparse recall with RRF, followed by CrossEncoder reranking and LLM relevance grading.

## Commands

```bash
.venv/bin/python -m compileall -q agent documents evaluation graph graph2 llm_models rag_service tools utils tests main.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/pip check
.venv/bin/python main.py
```

## Engineering rules

- Reusable modules must not call external services, connect to Milvus, load model weights, or enter a CLI loop during import.
- Create runtime dependencies through the lazy factories in `llm_models/`, `tools/`, and `rag_service/`.
- Add configuration to `rag_service.settings.Settings` and `.env.example`; never commit credentials or print `.env` values.
- Preserve the current CRM analyzer terms, Chinese sentence splitting, direct-answer route, reranker, and globally bounded Graph 2 retry policy unless a tested replacement is introduced.
- Add deterministic offline tests for policy and metric changes. Tests must not require credentials, network access, model downloads, or a running Milvus instance.
- Keep evaluation data versioned under `evaluation/datasets/`. Do not restore or overwrite user-deleted historical files under `test/recall_eval`.
- Do not copy numeric claims from the simulated documents into production defaults without evaluation or load-test evidence.

## Destructive ingestion warning

`MilvusVectorSave.create_collection()` is non-destructive. Destructive replacement requires an exact `DROP:<collection>` confirmation through `recreate_collection()`. Prefer `documents.ingest_markdown` over the legacy bulk loader so governed metadata and checkpoints are preserved.

## Known enterprise gaps

The engineering, evaluation, ingestion-governance, secure retrieval/citation, bounded workflow, API-contract, and reliability-observability baselines are present. The following are not yet production-complete:

- A live Milvus migration of legacy rows and production rehearsal of versioned alias release/rollback.
- Live migration and load evidence for tenant/ACL indexes, fusion settings, reranker timeout, and context budgets.
- A shared multi-instance production checkpointer and distributed conversation expiry worker; SQLite is the local/lightweight implementation.
- Exact provider cost telemetry, target-environment load evidence, calibrated SLOs, and a staged deployment rehearsal.

Dify, IAM, ONECRM writes, and approval execution are external systems. Represent them through versioned contracts and integration tests rather than implementing them inside this RAG core.
