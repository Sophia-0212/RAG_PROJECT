from __future__ import annotations

import argparse
import os


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Run the RAG HTTP service")
    parser.add_argument("--host", default=os.getenv("RAG_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("RAG_API_PORT", "8000")))
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    from rag_service.settings import get_settings

    if get_settings().state_backend == "sqlite" and args.workers != 1:
        parser.error("the SQLite runtime supports exactly one worker; use a shared checkpointer before scaling out")
    uvicorn.run("rag_service.api:create_app", factory=True, host=args.host, port=args.port, workers=args.workers)


if __name__ == "__main__":
    main()
