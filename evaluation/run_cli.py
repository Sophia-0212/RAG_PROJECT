from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from evaluation.assets import validate_assets
from evaluation.gate import evaluate_gate, load_rules
from evaluation.runner import PredictionError, run_evaluation
from evaluation.schema import DatasetError


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "datasets" / "ad_crm_golden_small_v1.jsonl"
DEFAULT_MANIFEST = ROOT / "corpus" / "ad_crm_v1" / "manifest.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and score an advertising-CRM RAG evaluation run")
    parser.add_argument("predictions", type=Path, help="JSONL predictions produced by the system under test")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--gate", type=Path, default=ROOT / "release_gate.json")
    parser.add_argument("--output", type=Path, default=None, help="Write the complete JSON report to this path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        assets = validate_assets(args.dataset, args.manifest)
        report = run_evaluation(args.dataset, args.predictions)
        gate = evaluate_gate(report["metrics"], load_rules(args.gate))
    except (DatasetError, PredictionError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"evaluation input error: {exc}") from exc

    report["assets"] = asdict(assets)
    report["gate"] = {"passed": gate.passed, "failures": list(gate.failures)}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if gate.passed else 1)


if __name__ == "__main__":
    main()
