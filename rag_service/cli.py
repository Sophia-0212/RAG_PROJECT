import argparse
import os
from uuid import uuid4

from rag_service.application import create_runtime


def main() -> None:
    from graph2.graph_2 import run_cli

    parser = argparse.ArgumentParser(description="Run the local RAG CLI")
    parser.add_argument("--tenant", default=os.getenv("RAG_CLI_TENANT_ID"))
    parser.add_argument("--user", default=os.getenv("RAG_CLI_USER_ID"))
    parser.add_argument("--principal", action="append", default=[])
    parser.add_argument("--conversation", default=None)
    args = parser.parse_args()
    if not args.tenant or not args.user:
        parser.error("--tenant and --user are required (or set RAG_CLI_TENANT_ID/RAG_CLI_USER_ID)")
    runtime = create_runtime()
    try:
        run_cli(
            runtime.graph,
            tenant_id=args.tenant,
            user_id=args.user,
            principal_ids=tuple(args.principal),
            conversation_id=args.conversation or str(uuid4()),
            conversation_store=runtime.conversations,
            settings=runtime.settings,
        )
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
