# Enterprise Capability Evidence

This index distinguishes implemented, testable repository behavior from claims that still require a real deployment.
The simulated Markdown documents are requirements input only and are not evidence of production results.

| Capability | Implementation evidence | Verification evidence | Status |
| --- | --- | --- | --- |
| Typed configuration and import-safe composition | `rag_service/settings.py`, `rag_service/application.py` | `tests/test_settings.py`, `tests/test_runtime_boundaries.py` | Implemented offline |
| Versioned evaluation and release gates | `evaluation/metrics.py`, `evaluation/gates.py`, `evaluation/release_gate.json` | `tests/test_evaluation.py`, `tests/test_release_gate.py` | Implemented offline; thresholds need live calibration |
| Governed incremental ingestion | `documents/governance.py`, `documents/ingestion_runner.py`, `documents/manifest_store.py` | `tests/test_ingestion_governance.py`, `tests/test_ingestion_runner.py` | Implemented offline; live migration pending |
| Non-destructive index release/rollback | `documents/index_release.py`, `documents/milvus_db.py` | `tests/test_milvus_lifecycle.py` | Policy tested; staging rehearsal pending |
| Tenant/ACL/effective-time filtering | `rag_service/security.py`, `tools/retriever_tools.py` | `tests/test_retrieval_security.py` | Deterministic negative tests pass; live Milvus proof pending |
| Score lineage, rerank fallback, bounded context | `rag_service/retrieval.py`, `rag_service/context.py`, `tools/reranker_tools.py` | `tests/test_retrieval_pipeline.py`, `tests/test_reranker.py` | Implemented offline; tuning pending |
| Structured answer citations | `rag_service/answer.py`, `graph2/generate_node2.py` | `tests/test_answer.py`, `tests/test_generation_policy.py` | Implemented offline |
| Bounded graph and stable termination | `rag_service/execution.py`, `graph2/graph_2.py` | `tests/test_execution.py`, `tests/test_graph2_policy.py` | Implemented offline |
| Durable tenant-bound conversations | `rag_service/checkpointing.py`, `rag_service/conversation.py` | `tests/test_conversation.py`, `tests/test_persistence.py` | SQLite single-process implementation |
| Versioned API and external boundaries | `rag_service/api.py`, `rag_service/contracts.py` | `tests/test_api.py`, `tests/test_contracts.py` | Implemented offline; live partner tests pending |
| Quota, concurrency, retry, breakers | `rag_service/resilience.py` | `tests/test_resilience.py`, `tests/test_service.py` | Implemented in-process |
| Redacted telemetry and metrics | `rag_service/telemetry.py`, `rag_service/api.py` | `tests/test_telemetry.py`, `tests/test_api.py` | Implemented offline |
| Reproducible performance report | `evaluation/performance.py`, `evaluation/load_test.py` | `tests/test_performance.py` | Harness implemented; production results pending |
| Hardened single-instance container | `Dockerfile`, `requirements.service.lock`, `deploy/docker-compose.yml`, `.dockerignore` | `tests/test_deployment.py`, CI image scan | Repository policy implemented; staging proof pending |
| Local state migration | `rag_service/migrations.py` | `tests/test_deployment.py` | Idempotence tested offline |
| Operations and rollback | `docs/operations.md`, `docs/deployment-runbook.md`, `docs/incident-runbook.md` | Release checklist and rehearsal record | Procedure defined; rehearsal pending |

## Commands that produce evidence

```bash
.venv/bin/python -m compileall -q agent documents evaluation graph graph2 llm_models rag_service tools utils tests main.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/pip check
.venv/bin/python -m evaluation.cli path/to/metrics.json
.venv/bin/python -m evaluation.load_test --help
.venv/bin/python -m rag_service.migrations --checkpoint-path /absolute/path/to/checkpoints.sqlite3
docker compose -f deploy/docker-compose.yml config --quiet
docker build --tag rag-enterprise-service:verification .
```

CI adds a Python dependency audit, CycloneDX SBOM generation, image vulnerability scan, and repository secret scan.
Keep the CI run URL, SBOM, image digest, evaluation output, and load report together as the release evidence package.

## Remaining release blockers

- Migrate governed metadata into a real Milvus environment and rehearse guarded alias promotion/rollback.
- Validate tenant/ACL indexes, hybrid fusion, reranker timeout, and context budgets with real distribution and load.
- Replace SQLite with a reviewed shared checkpointer and distributed expiry worker before multiple replicas.
- Complete live contract tests with IAM/gateway, LLM gateway, Dify, ONECRM, and approval owners.
- Record exact provider usage/cost where the provider contract supports it.
- Establish SLOs and alert thresholds from target-environment evaluation, load, soak, and incident evidence.
- Convert direct dependency pins into a platform-reviewed, hash-locked transitive supply-chain process if required by
  the deployment organization's policy.
