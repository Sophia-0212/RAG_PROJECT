from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from uuid import uuid4

from rag_service.application import create_runtime
from rag_service.auth import HttpRecoveryIdentityResolver
from rag_service.service import RAGService
from rag_service.settings import Settings, get_settings


logger = logging.getLogger(__name__)


class RecoveryWorker:
    def __init__(self, settings: Settings):
        if not settings.recovery_enabled:
            raise ValueError("RAG_RECOVERY_ENABLED must be true for the recovery worker")
        if not settings.recovery_authorization_url or not settings.recovery_authorization_token:
            raise ValueError("recovery authorization URL and token are required")
        self.settings = settings
        self.runtime = create_runtime(settings=settings)
        self.service = RAGService(self.runtime)
        self.resolver = HttpRecoveryIdentityResolver(
            settings.recovery_authorization_url,
            settings.recovery_authorization_token,
        )
        self.owner = f"worker:{socket.gethostname()}:{os.getpid()}:{uuid4()}"
        self.stopping = threading.Event()

    def close(self) -> None:
        self.runtime.close()

    def process_one(self) -> bool:
        try:
            return self.service.recover_next(self.resolver, owner=self.owner)
        except Exception as exc:
            logger.warning("recovery poll failed: %s", type(exc).__name__)
            return False

    def run(self, *, once: bool = False) -> None:
        futures: set[Future[bool]] = set()
        with ThreadPoolExecutor(
            max_workers=self.settings.recovery_concurrency,
            thread_name_prefix="rag-recovery",
        ) as executor:
            while not self.stopping.is_set():
                completed = {future for future in futures if future.done()}
                for future in completed:
                    future.result()
                futures -= completed
                while len(futures) < self.settings.recovery_concurrency and not self.stopping.is_set():
                    future = executor.submit(self.process_one)
                    futures.add(future)
                    if once:
                        break
                if once:
                    wait(futures)
                    for future in futures:
                        future.result()
                    return
                self.stopping.wait(self.settings.recovery_poll_seconds)
            if futures:
                wait(futures)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resume durable RAG request runs")
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    parser.add_argument("--check", action="store_true", help="check recovery dependencies and exit")
    return parser


def check_dependencies(settings: Settings) -> bool:
    from rag_service.checkpointing import create_checkpointer
    from rag_service.coordination import create_coordination
    from rag_service.run_store import PostgresRequestRunStore

    checkpoints = create_checkpointer(settings)
    coordination = None
    try:
        runs = PostgresRequestRunStore(checkpoints.resource)
        coordination, _ = create_coordination(settings)
        return checkpoints.ping() and runs.ping() and coordination.ping()
    finally:
        if coordination is not None:
            coordination.close()
        checkpoints.close()


def main() -> None:
    args = _parser().parse_args()
    settings = get_settings()
    settings.validate_service_startup(identity_provider_configured=True)
    if args.check:
        if not check_dependencies(settings):
            raise SystemExit(1)
        return
    worker = RecoveryWorker(settings)

    def stop(signum, frame) -> None:
        worker.stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        worker.run(once=args.once)
    finally:
        worker.close()


if __name__ == "__main__":
    main()
