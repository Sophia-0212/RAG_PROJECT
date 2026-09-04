from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Sequence


@dataclass(frozen=True)
class LoadSample:
    status_code: int
    latency_ms: float
    error_code: str = ""


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def summarize_load(samples: Sequence[LoadSample], *, elapsed_seconds: float) -> dict:
    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds must be positive")
    latencies = [sample.latency_ms for sample in samples]
    successes = [sample for sample in samples if 200 <= sample.status_code < 300]
    errors = Counter(sample.error_code or str(sample.status_code) for sample in samples if sample not in successes)
    return {
        "request_count": len(samples),
        "success_count": len(successes),
        "success_rate": round(len(successes) / len(samples), 6) if samples else 0.0,
        "throughput_rps": round(len(samples) / elapsed_seconds, 3),
        "latency_ms": {
            "min": round(min(latencies), 3) if latencies else 0.0,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "errors": dict(sorted(errors.items())),
        "samples": [asdict(sample) for sample in samples],
    }

