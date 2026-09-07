# Findings & Decisions

## Requirements
- Determine whether `http://127.0.0.1:4174/#/audit` is served from RAG_PROJECT.
- Inventory all functions in the mock enterprise knowledge-base management UI.
- Provide a business-oriented, safe experience guide that builds knowledge-operations intuition.

## Research Findings
- Port 4174 is served by Python process PID 85112.
- Repository search resolves `/audit` to `Prometheus/upload_mock/js/pages/audit.js`, registered by `js/app.js` and `js/core/router.js`.
- The UI explicitly states that settings and audit actions update in-memory mock state and reset on refresh.
- The mock data includes three workspaces: knowledge administrator, read-only auditor, and content operator.
- PID-specific `lsof` confirms the server working directory is `/Users/lixiaofei05/Desktop/workspace/RAG企业知识库项目/RAG_PROJECT`.
- The frontend is a dependency-free hash-routed static application under `Prometheus/upload_mock/`, with ten registered routes.
- Routes cover overview, source lifecycle, source creation, ingestion jobs, manual review, version release/rollback, offline quality evaluation, online-effect monitoring, audit evidence, and environment settings.
- Direct `/jobs/review` navigation has no job context; the meaningful review UI requires the failed job query parameter supplied by the Jobs page.
- Cross-cutting shell functions include workspace switching, global search, notifications, profile/role details, mock-state export, and mock-state reset.
- Source actions include search/filter, detail drawer, immediate sync, ACL editing, pause/resume, archive, permission health check, and a four-step source wizard.
- Job actions include search/filter, details/logs, cancellation, checkpoint retry, version navigation, and manual review for blocked complex tables.
- Version actions include details, candidate comparison, quality navigation, publish with quality gate, and rollback to retained versions.
- Quality actions include registering dataset metadata, starting a simulated evaluation, report inspection, and fixed gate visualization.
- Online-effect actions include time/version slicing, metric trends, A/B pause/resume, tenant/business/issue drill-down, failure-to-ticket flow, alert-rule CRUD/toggle, and dry-run rollback simulation.
- Audit actions include query/actor/result filters, evidence drawer, per-event JSON export, and filtered JSON/CSV export.
- Settings have infrastructure, model, connector, and security tabs; actions mutate mock state and produce audit events but do not touch infrastructure.
- The browser visibly labels the environment as simulated and the audit/settings pages explicitly state that state resets on refresh.
- A live admin evaluation completed after about 1.5 seconds and produced fixed scores (95.1 overall, 95.8 recall, 98.1 citation, 94.4 groundedness, zero ACL leakage), exactly matching the hard-coded mock API.
- Repeating the evaluation in the read-only auditor workspace was rejected and created a `PERMISSION_DENIED` audit containing actor, target action, source, request ID, timestamp, and retention metadata.
- Reloading restored the initial admin workspace and five seed audit events, confirming that the exercise did not persist or call the real RAG service.
- The quality page's 320/148/206-case datasets are narrative UI seed data, not execution of the repository's real `evaluation/` assets.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Treat all UI page text as mock evidence until backed by source behavior | Prevents presenting illustrative controls as real service integrations |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Generic process listing is sandbox-blocked | Confirm working directory with PID-specific `lsof` and correlate requested assets with the repository |
| Browser helper waited for a full page load on a hash-only route | Used the application's own hash routing semantics and CDP observation instead |

## Resources
- `Prometheus/upload_mock/js/app.js`
- `Prometheus/upload_mock/js/core/router.js`
- `Prometheus/upload_mock/js/core/data.js`
- `Prometheus/upload_mock/js/core/mock-api.js`
- `Prometheus/upload_mock/js/pages/*.js`
