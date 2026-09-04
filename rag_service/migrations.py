from __future__ import annotations

import argparse
import json

from rag_service.checkpointing import create_sqlite_checkpointer
from rag_service.conversation import ConversationStore
from rag_service.settings import get_settings


def migrate_local_state(path: str) -> dict[str, str]:
    """Create or migrate local checkpoint and conversation schemas idempotently."""
    checkpoints = create_sqlite_checkpointer(path)
    conversations = ConversationStore(path)
    try:
        conversations.prune_expired(checkpoints.saver)
        if not conversations.ping():
            raise RuntimeError("conversation schema verification failed")
        return {"checkpoint": "ready", "conversation": "ready"}
    finally:
        conversations.close()
        checkpoints.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate RAG service state schemas")
    parser.add_argument("--checkpoint-path", default=None)
    args = parser.parse_args()
    path = args.checkpoint_path or get_settings().checkpoint_path
    print(json.dumps(migrate_local_state(path), sort_keys=True))


if __name__ == "__main__":
    main()
