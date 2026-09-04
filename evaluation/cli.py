from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.gate import evaluate_gate, load_rules


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a metrics JSON file against release gates")
    parser.add_argument("metrics", type=Path, help="JSON object containing metric names and values")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("release_gate.json"),
        help="Release-gate configuration",
    )
    args = parser.parse_args()

    with args.metrics.open("r", encoding="utf-8") as handle:
        metrics = json.load(handle)
    if not isinstance(metrics, dict):
        parser.error("metrics must be a JSON object")

    report = evaluate_gate(metrics, load_rules(args.config))
    print(json.dumps({"passed": report.passed, "failures": report.failures}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
