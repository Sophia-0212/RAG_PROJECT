# Progress Log

## Session: 2026-09-04 to 2026-09-05

### Current Status
- **Phase:** core implementation and local verification complete
- **Remaining:** target-cluster Pod-kill, IAM integration, rolling-version and recovery load/soak evidence

### Implemented
- Added the PostgreSQL request ledger, request-scoped checkpoint threads, lease/fencing transitions, retry/expiry reconciliation, and idempotent conversation-turn finalization.
- Added the API fast path, stable request ID contract, pending/terminal responses, authenticated result polling, durable streaming cancellation, and dependency readiness.
- Added a dedicated bounded recovery worker with `SKIP LOCKED` claiming, heartbeat renewal, fresh IAM authorization, graceful drain, and two-replica Kubernetes baseline.
- Added graph/input compatibility checks, per-attempt deadline refresh, exponential backoff with deterministic jitter, maximum-attempt/expiry categories, and fail-closed IAM outcome classification.
- Updated README, ADR, operations, incident, deployment, external contract, evidence index, and the affected simulation documents under `test/001-016`.

### Verification Results
| Check | Result |
| --- | --- |
| Python compile + `git diff --check` | passed |
| Final offline unit/contract suite | 135 passed, 10 integration tests skipped by the explicit switch |
| Recovery/API focused suite after cancellation and IAM cases | 22 passed |
| Real local PostgreSQL/Redis integration suite | 9 passed |
| Schema migration readiness | checkpoint, conversation, and request-run stores ready |
| Recovery worker dependency probe | passed |

The real-dependency suite covers API/worker initial-claim isolation, cross-runtime pending-node resume, completed-step preservation, request idempotency, conversation ordering, lease takeover/fencing, one-turn finalization, maximum attempts, recovery expiry, Redis coordination/quota, state pruning, and SQLite migration. The PostgreSQL test cluster must use UTF-8; an initial SQL_ASCII cluster correctly exposed driver byte/string incompatibility and was replaced rather than handled in application code.

### Not Yet Claimed
- No actual Kubernetes Pod-kill has been run in the target staging cluster.
- No live enterprise IAM revocation drill or rolling graph-version drill has been run.
- No recovery-specific target-capacity soak or recovery SLO evidence has been produced.
- Therefore the repository proves the engineering baseline, not production HA or a measured automatic-recovery SLO.
