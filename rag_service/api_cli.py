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
    if args.workers != 1:
        parser.error("the SQLite runtime supports exactly one worker; use a shared checkpointer before scaling out")
    uvicorn.run("rag_service.api:create_app", factory=True, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
