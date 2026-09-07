"""Versioned offline evaluation primitives for the RAG service."""

from evaluation.assets import AssetReport, validate_assets
from evaluation.gate import GateReport, MetricRule, evaluate_gate
from evaluation.runner import Prediction, evaluate_predictions, run_evaluation
from evaluation.schema import EvalCase, load_dataset

__all__ = [
    "AssetReport",
    "EvalCase",
    "GateReport",
    "MetricRule",
    "Prediction",
    "evaluate_gate",
    "evaluate_predictions",
    "load_dataset",
    "run_evaluation",
    "validate_assets",
]
