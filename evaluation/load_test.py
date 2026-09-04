from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from evaluation.performance import LoadSample, summarize_load


def _send(url: str, body: bytes, headers: dict[str, str], timeout: float) -> LoadSample:
    started = time.perf_counter()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    status_code = 0
    error_code = ""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
            response.read()
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            error_code = str(payload.get("error", {}).get("code", "HTTP_ERROR"))
        except Exception:
            error_code = "HTTP_ERROR"
    except Exception as exc:
        error_code = type(exc).__name__
    return LoadSample(
        status_code=status_code,
        latency_ms=(time.perf_counter() - started) * 1000,
        error_code=error_code,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a measured RAG API load report")
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/query")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--principal", action="append", default=[])
    parser.add_argument("--question", default="你好")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.requests <= 0 or args.concurrency <= 0 or args.timeout <= 0:
        parser.error("requests, concurrency, and timeout must be positive")

    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": args.tenant,
        "X-User-ID": args.user,
        "X-Principal-ID": ",".join(args.principal),
    }
    bodies = [
        json.dumps(
            {"question": args.question, "conversation_id": f"load-{uuid4()}"},
            ensure_ascii=False,
        ).encode("utf-8")
        for _ in range(args.requests)
    ]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        samples = list(executor.map(lambda body: _send(args.url, body, headers, args.timeout), bodies))
    report = summarize_load(samples, elapsed_seconds=time.perf_counter() - started)
    report.update(
        {
            "schema_version": "rag-load-report-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_url": args.url,
            "configured_concurrency": args.concurrency,
            "configured_timeout_seconds": args.timeout,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
