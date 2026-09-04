# Task Plan: RAG 企业级差距分析

## Goal
基于真实 RAG_PROJECT 源码与 16 份目标文档，按已确认路线逐步补齐可验证的企业级 RAG 能力，并保留用户现有修改。

## Next Step
八个实施模块已完成；下一阶段按证据索引在目标环境执行 Milvus、IAM、LLM 和负载验证。

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints
- [x] Revalidate repository baseline and current worktree
- **Status:** complete

### Phase 2: Target Capability Model
- [x] Extract enterprise-RAG requirements from the 16 target documents
- [x] Separate RAG-engine scope from Dify, CRM, IAM, and infrastructure scope
- **Status:** complete

### Phase 3: Evidence-Based Code Audit
- [x] Trace ingestion, retrieval, reranking, graph, API, security, observability, evaluation, and operations
- [x] Classify each capability as implemented, partial, absent, or external
- **Status:** complete

### Phase 4: Gap and Risk Prioritization
- [x] Identify blockers for a credible enterprise-grade project
- [x] Rank gaps by production risk, dependency, effort, and demonstrability
- **Status:** complete

### Phase 5: Modular Execution Roadmap
- [x] Group implementation into large, dependency-ordered modules
- [x] Define goals, scope, outputs, acceptance criteria, and non-goals for each module
- [x] Deliver the proposed execution sequence without changing business code
- **Status:** complete

### Phase 6: Module 1 - Engineering Baseline
- [x] Inventory runtime imports, configuration, entrypoints, and dependency requirements
- [x] Introduce a locked/declared project configuration and typed settings boundary
- [x] Remove import-time requests, database connections, model loading, and CLI loops from reusable modules
- [x] Establish a canonical application composition boundary around Graph 2
- [x] Add developer documentation and offline import/configuration tests
- **Status:** complete

### Phase 7: Module 2 - Evaluation Baseline
- [x] Design a small versioned evaluation schema without restoring deleted user files
- [x] Add deterministic unit tests for metrics and critical graph/retrieval policies
- [x] Add CI commands and an initial release-gate configuration
- [x] Run the offline test suite and record remaining environment-dependent gaps
- **Status:** complete

### Phase 8: First Implementation Handoff
- [x] Review the resulting diff for accidental overlap with user changes
- [x] Document completed scope, verification, and the next module boundary
- **Status:** complete

### Phase 9: Module 3 - Enterprise Ingestion and Index Governance
- [x] Define stable source/document/chunk/version identity and governed metadata contracts
- [x] Add deterministic change planning for upsert, unchanged, tombstone, and delete operations
- [x] Add resumable checkpoints and idempotent ingestion-run state
- [x] Replace implicit collection recreation with explicit non-destructive lifecycle methods
- [x] Add offline tests for identity, duplicate ingestion, update, deletion, resume, and rollback planning
- [x] Document migration limits and verify the complete offline suite
- **Status:** complete

### Phase 10: Module 4 - Secure Retrieval, Context, and Citations
- [x] Define request identity, query constraints, retrieval candidates, context blocks, and citation contracts
- [x] Build fail-closed tenant/ACL/status/effective-time filters with injection-safe literals
- [x] Preserve recall and rerank scores, deduplicate versions, and add reranker timeout/fallback behavior
- [x] Add deterministic parent expansion and token-budgeted context packing
- [x] Return structured answer/citation output from the Graph 2 generation path
- [x] Add negative ACL, fallback, context-budget, and citation tests
- **Status:** complete

### Phase 11: Module 5 - Bounded Workflow and Durable Conversations
- [x] Define serializable execution budgets, counters, reason codes, and no-progress detection
- [x] Refactor Graph 2 routing so every retry path has an explicit terminal condition
- [x] Preserve original queries and record query/candidate lineage across retries
- [x] Add durable LangGraph SQLite checkpoints and tenant-bound conversation metadata
- [x] Add conversation expiry/pruning and restart recovery behavior
- [x] Add deterministic budget, termination, isolation, and persistence tests
- **Status:** complete

### Phase 12: Module 6 - Service API and External Contracts
- [x] Define versioned request/response/error schemas and authentication headers
- [x] Expose query, stream, conversation, liveness, and readiness endpoints
- [x] Propagate tenant/user/principal/request/conversation context end to end
- [x] Add cancellation-aware streaming and stable failure mapping
- [x] Define Dify, IAM, CRM, and approval integration boundaries without absorbing external responsibilities
- [x] Add offline API and contract tests and document the service boundary
- **Status:** complete

### Phase 13: Module 7 - Observability, Reliability, and Performance Evidence
- [x] Define redacted structured events, trace lineage, and bounded metric labels
- [x] Instrument service and graph execution without recording prompts or unauthorized text
- [x] Add per-tenant quotas, global concurrency control, retries with jitter, and circuit breakers
- [x] Define and test dependency-specific degradation behavior
- [x] Add deterministic fault tests and a reproducible load-report command
- [x] Document measured evidence separately from target SLOs
- **Status:** complete

### Phase 14: Module 8 - Deployment, Security Hardening, and Evidence
- [x] Add a pinned, non-root, health-checked service image and minimal build context
- [x] Add startup/profile validation that rejects unsafe production defaults
- [x] Add schema/index migration, staged release, rollback, and incident runbooks
- [x] Extend CI with package, image, dependency, secret, and vulnerability checks
- [x] Produce an evidence index mapping enterprise claims to executable proof
- [x] Run final offline verification and document environment-dependent gaps
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Treat live source as authoritative | The target documents describe a simulated system and may overstate or misplace responsibilities |
| Separate in-repo gaps from external-system contracts | A RAG core engine should not absorb Dify, ONECRM, IAM, or platform responsibilities without clear boundaries |
| Require file/line evidence for implementation claims | Prevents turning simulated capabilities into unsupported resume/project claims |
| Keep this turn read-only for business code | The user requested analysis and an execution plan first |
| Use Graph 2 as the future canonical orchestration baseline | It already contains the most complete route/retrieve/rerank/grade/generate loop; Graph 1 should remain a demo or comparison baseline |
| Start evaluation alongside engineering cleanup | Later retrieval, graph, and performance changes need a reproducible baseline before parameters are tuned |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Plan initialization emitted a `C.UTF-8` locale warning | Non-blocking on macOS; planning files were created successfully |
| First lazy-initialization patch duplicated a `collection_name` keyword in the Milvus debug entrypoint | Removed the stale keyword before continuing and reran static compilation |
| A resumed patch expected pre-refactor Graph 2 imports that had already changed | Re-read the files, confirmed the intended changes were present, and applied only the remaining Graph 1 edits |
| Import-safety check found LangChain 1.3 no longer exports the legacy agent helpers | Imported the legacy demo from the installed `langchain-classic` compatibility package and pinned it explicitly |
| One Graph 1 patch request contained an invalid control character | The patch was rejected without file changes; split it into smaller valid patches |
| `pip check` found incompatible installed transitive dependencies (`wrapt` and `milvus-lite`) | Upgraded to `wrapt 2.1.1`, `milvus-lite 3.1.0`, and Langfuse 4.15.1; pinned the compatible set for revalidation |
| Secure-generation test found `tiktoken` downloads its vocabulary on first use | Made the default token counter a conservative offline estimator and retained `tiktoken` only as an explicit optional counter |
