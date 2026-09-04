from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class GateConfigError(ValueError):
    """Raised when release-gate configuration is invalid."""


@dataclass(frozen=True)
class MetricRule:
    metric: str
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if not self.metric:
            raise GateConfigError("Metric name must not be empty")
        if self.minimum is None and self.maximum is None:
            raise GateConfigError(f"Metric {self.metric!r} needs a minimum or maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise GateConfigError(f"Metric {self.metric!r} has minimum greater than maximum")


@dataclass(frozen=True)
class GateReport:
    passed: bool
    failures: tuple[str, ...]


def load_rules(path: str | Path) -> list[MetricRule]:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        raise GateConfigError("Gate configuration must contain a rules list")

    rules: list[MetricRule] = []
    for item in raw["rules"]:
        if not isinstance(item, dict):
            raise GateConfigError("Each gate rule must be an object")
        rules.append(
            MetricRule(
                metric=item.get("metric", ""),
                minimum=item.get("minimum"),
                maximum=item.get("maximum"),
            )
        )
    if not rules:
        raise GateConfigError("At least one gate rule is required")
    return rules


def evaluate_gate(metrics: Mapping[str, float], rules: Sequence[MetricRule]) -> GateReport:
    failures: list[str] = []
    for rule in rules:
        value = metrics.get(rule.metric)
        if value is None:
            failures.append(f"missing metric: {rule.metric}")
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            failures.append(f"invalid metric: {rule.metric}={value!r}")
            continue
        if rule.minimum is not None and value < rule.minimum:
            failures.append(f"{rule.metric}={value:.4f} below minimum {rule.minimum:.4f}")
        if rule.maximum is not None and value > rule.maximum:
            failures.append(f"{rule.metric}={value:.4f} above maximum {rule.maximum:.4f}")
    return GateReport(passed=not failures, failures=tuple(failures))
