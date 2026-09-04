"""Versioned offline evaluation primitives for the RAG service."""

from evaluation.gate import GateReport, MetricRule, evaluate_gate
from evaluation.schema import EvalCase, load_dataset

__all__ = ["EvalCase", "GateReport", "MetricRule", "evaluate_gate", "load_dataset"]
