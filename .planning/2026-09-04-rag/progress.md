# Progress Log

## Session: 2026-09-04

### Current Status
- **Phase:** 14 - Deployment, security hardening, and evidence
- **Started:** 2026-09-04

### Actions Taken
- Read the planning skill and restored the completed repository-index context.
- Created an isolated enterprise-gap-analysis planning session.
- Recorded the read-only analysis scope and evidence requirements.
- Revalidated branch and dirty-worktree state without modifying user files.
- Inventoried the live repository and confirmed the current evaluation assets are deleted from the worktree.
- Reviewed current staged Python changes and extracted the main target-document capability categories.
- Completed repository baseline discovery and started target capability modeling.
- Audited live configuration, model factories, logging, parser, Milvus schema, and ingestion pipeline.
- Recorded service-entry, lifecycle, schema, incremental-ingestion, deletion, ACL, and chunking gaps.
- Audited retriever, reranker, tool-calling agent, and Graph 1 source.
- Confirmed a credible hybrid retrieval/rerank skeleton alongside major ACL, citation, budget, persistence, lifecycle, and fallback gaps.
- Audited all Graph 2 state, routing, retrieval, grading, generation, retry, web-search, and CLI code.
- Identified Graph 2 as the preferred production-flow base, with gaps in durable state, global budgets, provenance, structured citations, evaluator rigor, and loop safety.
- Audited Langfuse compose configuration, repository documentation, and codebase-wide enterprise-control keywords.
- Confirmed the absence of a production service/deployment/testing baseline and noted significant documentation drift.
- Read the full target RAG, evaluation, performance/degradation, observability/SLO, and incident sections.
- Completed target capability modeling and separated RAG-owned controls from workflow/CRM-owned controls.
- Statically parsed all 38 live Python files with zero syntax errors.
- Confirmed no live production packaging, service, CI, or executable test baseline.
- Completed the implemented/partial/absent/external capability classification and started risk prioritization.
- Ranked the gaps into P0/P1/P2 using production risk and dependency order.
- Defined eight implementation modules with scope, outputs, acceptance criteria, and external-system non-goals.
- Completed the analysis-only roadmap without modifying business code or restoring user-deleted files.
- User approved implementation; started the first implementation batch covering Modules 1 and 2.
- Audited current import dependencies and confirmed reusable modules eagerly initialize LLM, embeddings, Milvus, reranker, or CLI behavior.
- Corrected the virtual-environment path to `.venv/bin/python`; it uses Python 3.11.15 and contains the runtime dependencies but no test runner.
- Added the typed settings package, application/CLI composition boundary, environment template, project metadata, and pinned direct dependency file.
- Converted model, embedding, parser, Milvus, retriever, and reranker construction to lazy factories; fixed a duplicate keyword caught by static compilation.
- Converted Graph 2, Graph 1, and the legacy agent to explicit builders/CLI entrypoints while retaining the user's direct-answer, rerank, and retry work.
- Verified all core modules import and Graph 2 compiles without API keys, a reachable Milvus service, or eager model loading.
- Added a versioned five-case CRM smoke dataset, deterministic retrieval/citation/leakage metrics, a six-rule release gate, and a CLI gate evaluator.
- Added offline configuration, dataset, metrics, gate, runtime-boundary, reranker, parser, and Graph 2 policy tests plus CI workflow.
- Passed 23 offline tests, source compilation, diff whitespace checks, project metadata parsing, and wheel metadata generation.
- Resolved pre-existing dependency conflicts by upgrading Langfuse to 4.15.1, `wrapt` to 2.1.1, and `milvus-lite` to 3.1.0; `pip check` now reports no broken requirements.
- Confirmed the user's staged CRM analyzer, direct-answer, reranker, response-format, and retry behavior remains present; user-deleted historical evaluation files were not restored.
- Added stable governed source/document/version/chunk identities, version-sensitive ACL/effective metadata, deterministic change planning, atomic manifests, failure checkpoints, and resumable execution.
- Replaced implicit Milvus recreation with non-destructive ensure, exact-confirmation recreation, versioned collection creation, guarded alias switch/rollback, and chunk-ID idempotent upsert.
- Added governed Markdown ingestion CLI and 14 ingestion/lifecycle tests; the full offline suite now passes 37 tests.
- Added fail-closed retrieval security, score lineage, parent expansion, bounded contexts, structured citations, and reranker fallback; the full suite reached 48 tests.
- Replaced Graph 2's independent retry loops with global step/retrieval/generation/rewrite/web/token/deadline budgets and stable terminal reason codes.
- Added immutable query and candidate lineage, repeated-state termination, clarification for context-free follow-ups, and component-version state.
- Added strict-allowlist SQLite checkpoints, tenant/user-bound conversation metadata, bounded summaries, TTL pruning, and CLI restart recovery.
- Verified 59 offline tests, including process-restart restoration of real RAG state types, with clean dependency and compilation checks.
- Added FastAPI query/SSE/conversation/health endpoints, trusted-development-header and injectable-production IAM boundaries, request IDs, stable errors, and one-worker SQLite enforcement.
- Added a Dify adapter plus explicit IAM, ONECRM, and approval ownership contracts; raw candidates and conversation summaries remain outside API responses.
- Verified the versioned OpenAPI contract and 70 offline tests with clean dependency, compilation, and whitespace checks.
- Added allowlist-redacted structured events, bounded-label Prometheus metrics, request/action latency, candidate/citation lineage, and `/metrics`.
- Added global concurrency control, bounded per-tenant token buckets, jittered retries, dependency circuit breakers, and Reranker fail-open-to-authorized-recall behavior.
- Added a reproducible API load-report command and an explicit failure matrix without importing simulated SLO numbers.
- Verified 82 offline tests and application runtime composition with clean dependency, compilation, metadata, and whitespace checks.
- Added a digest-pinned, non-root, health-checked single-worker production image, read-only Compose baseline, required secret/model mounts, and fail-fast production configuration validation.
- Added a 32-character gateway-secret floor, restored the broken readiness response, and covered both with deterministic API/configuration tests.
- Added idempotent local-state migration plus deployment, guarded index promotion, rollback, incident, and evidence runbooks.
- Extended CI with dependency audit, CycloneDX SBOM, image vulnerability scanning, and repository secret scanning; removed example weak secrets from the local Langfuse stack.
- Split query-service dependencies from ingestion dependencies and pinned the official CPU-only PyTorch build; omitted the unused local Milvus engine from the remote-Milvus image.
- Built the ARM64 Linux image successfully as `sha256:bf5296a9ece37293bdd91baa994000b2cbea5c538758c7a2037e8815d7626fc2` (1,111,674,216 bytes) and verified UID 10001 plus API/Milvus imports inside the container.
- Verified 94 offline tests, production Compose parsing, source compilation, dependency consistency, package metadata, and whitespace checks.
- Started the development API at `http://127.0.0.1:8011`; liveness, readiness, and OpenAPI returned HTTP 200, while an unauthenticated query returned the stable 401 authentication envelope.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Python compileall | All maintained source compiles | Passed with no errors | PASS |
| Offline unittest suite | No LLM/Milvus/Web dependency and all assertions pass | 94 tests passed in 5.466s | PASS |
| Import/build isolation | Core imports and Graph 2 build without network | Passed in a socket-blocked subprocess | PASS |
| Package metadata | `pyproject.toml` can produce wheel metadata | Generated `rag_enterprise_service-0.1.0.dist-info` in a temporary directory | PASS |
| Git diff whitespace | No whitespace errors | `git diff --check` returned no findings | PASS |
| Production Compose | All required settings resolve and YAML is valid | `docker compose ... config --quiet` passed with synthetic values | PASS |
| Production image | Linux image builds and runs as non-root | Built ARM64 image; UID 10001 and runtime imports verified | PASS |

### Errors
| Error | Resolution |
|-------|------------|
| `C.UTF-8` locale warning | Non-blocking; plan initialization succeeded |
| Initial image build selected CUDA-enabled PyTorch and multi-gigabyte GPU libraries | Split service dependencies and installed pinned PyTorch from the official CPU wheel index |
| Two Docker downloads returned incomplete artifacts with hash mismatches | Kept hash verification enabled, removed the unused `milvus-lite`/`pyarrow` chain from the remote-Milvus service image, and rebuilt successfully |
