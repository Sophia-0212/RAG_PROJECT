# Findings & Decisions

## Requirements
- User asks where knowledge is uploaded and whether a frontend currently exists.
- Inspect the whole project before deciding what the frontend should look like.
- Build a simulated frontend under Prometheus/upload_mock.
- Reflect Baidu Ads delivery-platform CRM business understanding and maintain technical rigor.
- Verify through ego-browser after implementation.
- Expand every business navigation item into a real page where practical.
- Apply modular frontend architecture with reusable components and page templates.
- Every visible interactive control must execute a meaningful mock behavior, not merely display a placeholder toast.
- Add a complete manual-review workbench so learners can build intuition by resolving the three complex-table anomalies instead of blindly retrying.

## Research Findings
- No knowledge-upload frontend currently exists. Prometheus contains an observability dashboard, not ingestion UI.
- No upload/ingest HTTP endpoint exists in rag_service/api.py; exposed APIs cover query, streaming query, request status, conversations, Dify integration, health, and metrics.
- The current governed ingestion entry point is CLI: `python -m documents.ingest_markdown <source_dir> ...`.
- Current source support is recursive Markdown directory scanning (`*.md`) via MarkdownSourceAdapter. PDFs exist in the repo but the governed CLI does not ingest them.
- Required CLI governance inputs are tenant plus either one or more ACL principals or public visibility. Optional inputs include run ID, chunker version, state directory, collection version, and alias activation.
- The CLI scans sources, parses/chunks them, calculates a manifest diff, writes operations with resumable checkpoints, saves the next manifest, and optionally switches a Milvus alias.
- An authoritative snapshot means missing documents become deletions/tombstones; this is operationally important and should be visible before execution.
- SourceDocument stable version identity changes when content, title, ACL, visibility, status, effective-time bounds, or governance schema changes.
- A production-like UI should therefore be a knowledge operations/release console, not a simple file-storage upload screen.
- New UI must label execution as simulated because the repository provides no ingestion control-plane API.
- Primary users inferred from the simulation documents: knowledge operations staff maintain sources and audit consistency; product/content owners supply changes; backend/platform engineers help diagnose pipeline failures.
- Representative failure modes to surface in UI: stale superseded chunks, missing-source deletions, duplicate documents, mixed-semantics chunks, and malformed complex tables.
- CRM application users are operations, sales support, and customer success staff seeking product policies, customer assignment rules, operating SOPs, and troubleshooting knowledge.
- The safe production direction is versioned collection build followed by guarded alias activation; rollback must reject stale observed state.
- The current upload mock is a single 329-line HTML, 473-line stylesheet, and 409-line script. Navigation outside Knowledge Sources is implemented only as placeholder toasts.
- No package.json, Vite, Webpack, or TypeScript configuration exists in the repository.
- The sibling Prometheus dashboard already uses native browser ES modules split into engine, scenario, component, and utility modules.
- `System` is a sidebar section label, not a business page. `Environment Settings` is the actual route beneath it.
- Page set: Operations Overview, Knowledge Sources, Ingestion Jobs, Version Releases, Quality Evaluation, Permission Audit, and Environment Settings.
- Cross-page lifecycle should be: onboard/configure source -> preflight/create job -> execute/resume -> create candidate collection -> run quality gate -> activate alias -> retain rollback target -> emit audit event/notification.
- Manual review should be scoped to a failed ingestion run and must require an explicit decision for every blocked artifact before checkpoint retry is allowed.
- The failed job currently contains only a free-text error; there is no review-case collection, original/parsed comparison, decision state, or completion marker.
- `retryJob` currently gates only on failed/canceled status, so review-required jobs can be retried without remediation.
- `jobs.js` currently renders failed and canceled runs with the same retry action in both the table and detail drawer; review-required failures need a distinct path into the workbench.
- The workbench will use `/jobs/review?job=<id>` as a job subflow, keeping the existing sidebar information architecture unchanged.
- `app.js` provides the page registry and the hash router uses exact paths, so the new child route can be added without changing other page contracts.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Design three stages: source upload, governance configuration, preflight/release | These map directly to adapter, governance, plan, checkpoint, and alias concepts. |
| Default to restricted visibility | The backend does this and CRM documents may contain sensitive operational knowledge. |
| Make destructive snapshot semantics explicit | Missing files can create DELETE operations, so operators need a preflight summary before publishing. |
| Do not claim PDF/DOCX support as implemented | Current governed adapter only scans Markdown. The mock may visually mark future formats as unavailable. |
| Use a light, dense enterprise console | It aligns with repeated operational work and contrasts clearly with the existing dark observability dashboard. |
| Make current online alias/version prominent | Stale-index incidents are a central business risk in the project's ingestion narrative. |
| Include task history and a details view | Checkpoint/resume and auditability are first-class backend semantics. |
| Keep the mock dependency-free | A static page is easy to inspect and run without changing the Python project. |
| Refactor to native ES modules | This matches the repository's existing frontend pattern and provides modularity without a build tool. |
| Use a shared AppShell plus route outlet | Sidebar/topbar/search/notifications/account UI should not be duplicated across pages. |
| Use a central normalized mock store persisted in localStorage | Cross-page actions need durable, internally consistent simulated state and a deterministic reset option. |
| Put business transitions behind a mock API | Pages should consume contracts with latency/failure behavior instead of directly rewriting unrelated page DOM. |
| Treat all visible controls as an acceptance inventory | A control is complete only when its success, failure, disabled, and confirmation behavior can be verified. |
| Model review as per-anomaly decisions | Operators need original/parsed comparison, remediation choice, corrected output, notes, and audit evidence for each flagged table. |
| Gate retry on submitted review completion | A failed run that requires human review must reject retry until every anomaly is resolved and the review batch is submitted. |
| Present a three-column review workbench | A queue, artifact comparison, and decision panel let an operator keep task context while resolving anomalies one by one. |
| Support normalize, exclude, and escalate decisions | These cover the three realistic outcomes: repair usable knowledge, deliberately omit unsafe content, or route an unsupported structure to engineering. |
| Keep the failed status until retry starts | Human review resolves the blocker but does not itself write vectors; the run remains failed/blocked until the operator resumes it from its checkpoint. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| First plan-status patch did not match an expected line | Re-read current files and reapplied a narrower patch; no product files were affected. |
| Manual-review findings patch used wording not present in the file | Re-read the file tail and applied the addition at the actual research section; no product files were affected. |
| Combined plan/progress status patch missed the progress heading text | Re-read both files and applied an exact section patch; no product files were affected. |
| Semantic click on the below-fold batch-submit button did not dispatch in ego-browser | Verified the live button was enabled, used one DOM click to diagnose, then confirmed the resulting modal through a fresh semantic snapshot and semantic button click. |
| Overview route check loaded a cached pre-change ES module | The old risk target routed to `/jobs`, so the workbench-only selector was absent; force an ignore-cache reload before retesting the new direct route. |
| Unmatched shell glob while probing framework files | Used exact-name find predicates and confirmed the absence of a frontend build chain. |

## Resources
- README.md
- documents/* ingestion pipeline
- rag_service/api.py and api_models.py
- deployment and business simulation docs
