# Findings & Decisions

## Requirements
- Production target is 18 workspaces, 640 registered/190 DAU, 4,600 RAG requests/day, peak 9 QPS, Kubernetes across three availability zones.
- Production must use shared PostgreSQL state and Redis coordination; SQLite remains local/test only.
- Add three-replica Kubernetes baseline and Docker Compose integration environment.
- Provide a resumable SQLite-to-PostgreSQL migration using a short maintenance window.
- Synchronize test/001 through test/016 with the implemented architecture without presenting simulated metrics as measured evidence.

## Research Findings
- Current runtime directly constructs one SqliteSaver and one SQLite ConversationStore against the same file.
- Current CLI intentionally rejects more than one Uvicorn worker and Docker runs one worker with a local state volume.
- Current per-conversation locks and tenant token buckets are process-local and cannot coordinate replicas.
- LangGraph officially positions SqliteSaver for lightweight/local use and PostgresSaver for durable production use.
- PostgresSaver 3.1.2 is compatible with the installed langgraph-checkpoint 4.2.0 and accepts psycopg ConnectionPool.
- PostgresSaver setup requires autocommit and dict_row; production runtime should not have DDL responsibility.
- Current baseline is 94 passing offline unittest cases.
- Existing worktree contains user-authored documentation renames/edits that must be preserved.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Production requires both RAG_DATABASE_URL and RAG_REDIS_URL | Prevents accidental fallback to process-local state |
| Redis lease with owner token and renewal | Serializes one conversation across replicas without holding a database transaction over LLM calls |
| PostgreSQL custom conversation repository | Provides atomic ownership checks and shared metadata |
| Separate migration command | Keeps DDL privileges out of the query-serving runtime |
| Read-only SQLite migration source | Protects rollback artifact during cutover |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| SQLite and PostgreSQL saver schemas differ | Replay deserialized checkpoints in parent order and migrate pending writes through saver APIs |
| SQLite pending writes lack task_path | Preserve available task_id/channel/value and use the public default empty task_path |

## Resources
- https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres
- https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx
