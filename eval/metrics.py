"""Pure metric helpers for Day 8 eval (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Confusion:
    """Binary confusion counts for flag presence."""

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def add(self, expected: bool, predicted: bool) -> None:
        if expected and predicted:
            self.tp += 1
        elif expected and not predicted:
            self.fn += 1
        elif not expected and predicted:
            self.fp += 1
        else:
            self.tn += 1

    def merge(self, other: Confusion) -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.tn += other.tn
        self.fn += other.fn

    @property
    def support(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def precision(self) -> float | None:
        denom = self.tp + self.fp
        return (self.tp / denom) if denom else None

    @property
    def recall(self) -> float | None:
        denom = self.tp + self.fn
        return (self.tp / denom) if denom else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)

    def as_dict(self) -> dict:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "support": self.support,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass
class ComplianceMetrics:
    """Overall + per-check_type confusion."""

    overall: Confusion = field(default_factory=Confusion)
    by_check_type: dict[str, Confusion] = field(default_factory=dict)
    severity_matches: int = 0
    severity_compared: int = 0

    def as_dict(self) -> dict:
        return {
            "overall": self.overall.as_dict(),
            "by_check_type": {
                k: v.as_dict() for k, v in sorted(self.by_check_type.items())
            },
            "severity_accuracy": (
                (self.severity_matches / self.severity_compared)
                if self.severity_compared
                else None
            ),
            "severity_compared": self.severity_compared,
        }


def score_compliance(
    *,
    expected_rows: Iterable[tuple[tuple[str, str, str], bool, str | None]],
    predicted_keys: set[tuple[str, str, str]],
    predicted_severity: dict[tuple[str, str, str], str] | None = None,
) -> ComplianceMetrics:
    """Score labeled golden rows against predicted finding keys.

    ``expected_rows``: ``((contract_id, clause_id, check_type), expected_flag, severity)``
    ``predicted_keys``: set of keys where the system emitted a finding.
    """
    metrics = ComplianceMetrics()
    sev_map = predicted_severity or {}

    for key, expected_flag, expected_severity in expected_rows:
        predicted = key in predicted_keys
        metrics.overall.add(expected_flag, predicted)
        check_type = key[2]
        bucket = metrics.by_check_type.setdefault(check_type, Confusion())
        bucket.add(expected_flag, predicted)

        if expected_flag and predicted and expected_severity:
            metrics.severity_compared += 1
            if sev_map.get(key) == expected_severity:
                metrics.severity_matches += 1

    return metrics


def quote_valid_rate(
    findings: Iterable[dict],
    clauses_by_id: dict[str, str],
    *,
    fuzzy: bool = True,
) -> dict:
    """Fraction of findings whose evidence_quote appears in the clause text."""
    from src.verifier.rules import quote_in_clause

    total = 0
    valid = 0
    for finding in findings:
        total += 1
        clause_id = str(finding.get("clause_id") or "")
        quote = str(finding.get("evidence_quote") or "")
        clause_text = clauses_by_id.get(clause_id, "")
        if quote_in_clause(quote, clause_text, fuzzy=fuzzy):
            valid += 1

    return {
        "findings": total,
        "quote_valid": valid,
        "quote_valid_rate": (valid / total) if total else None,
    }


def fmt_rate(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile for ``p`` in ``[0, 100]`` (inclusive)."""
    if not values:
        return None
    if p < 0 or p > 100:
        raise ValueError(f"percentile must be in [0, 100], got {p}")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    # Nearest-rank: index = ceil(p/100 * n) - 1
    rank = max(1, int((p / 100.0) * len(ordered) + 0.999999999))
    return ordered[min(rank, len(ordered)) - 1]


def latency_p95(latencies_sec: list[float]) -> float | None:
    """P95 wall-clock seconds across per-contract (or per-run) timings."""
    return percentile(latencies_sec, 95.0)
