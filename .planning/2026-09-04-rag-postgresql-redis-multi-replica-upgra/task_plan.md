# Task Plan: RAG PostgreSQL/Redis Multi-Replica Upgrade

## Goal
Upgrade the RAG service from a SQLite-only single-process runtime to a dual-mode architecture: SQLite for local/offline use and PostgreSQL plus Redis for a three-replica production baseline, with migration, tests, deployment artifacts, and synchronized 001-016 simulation documents.

## Next Step
Deliver the verified implementation and remaining live-environment gaps.

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints
- [x] Document in findings.md
- **Status:** complete

### Phase 2: Core Runtime and State Backends
- [x] Add typed backend, PostgreSQL, Redis, and pool settings
- [x] Add SQLite/PostgreSQL checkpoint and conversation factories
- [x] Add local/Redis quota and conversation coordination
- [x] Wire lifecycle, readiness, errors, and metrics
- **Status:** complete

### Phase 3: Migration and Deployment
- [x] Add schema and SQLite-to-PostgreSQL migration commands
- [x] Add PostgreSQL/Redis Compose integration profile
- [x] Add hardened three-replica Kubernetes baseline
- [x] Update dependency locks and CI
- **Status:** complete

### Phase 4: Tests and Verification
- [x] Preserve all offline tests and add backend unit tests
- [x] Add PostgreSQL/Redis integration and migration tests
- [x] Add deployment contract and state load tests
- [x] Run offline, integration, packaging, and deployment checks
- **Status:** complete

### Phase 5: Documentation and Delivery
- [x] Update README and enterprise operations/evidence docs
- [x] Update every simulation document 001-016
- [x] Run consistency scan and final review
- [x] Deliver verified result and remaining live-environment gaps
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| PostgreSQL persistence plus Redis coordination | Required for shared state, cross-Pod locking, and global tenant quota |
| Keep SQLite local backend | Maintains fast deterministic offline tests and developer ergonomics |
| Sync PostgresSaver with psycopg pool | Existing graph execution is synchronous and already runs in a thread pool |
| One worker per Pod, three Pods | Avoids duplicate in-process model memory while providing multi-AZ replication |
| Short maintenance-window migration | Clear consistency and rollback boundary without dual-write complexity |
| Compose-backed integration tests | Proves real SQL, pool, and Lua behavior while keeping default tests offline |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| zsh empty-glob parse error during discovery | Replaced shell glob loop with find-based inspection |
