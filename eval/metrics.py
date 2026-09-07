"""Pure metric helpers for Day 8 eval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def add(self, predicted: bool, expected: bool) -> None:
        if predicted and expected:
            self.tp += 1
        elif predicted and not expected:
            self.fp += 1
        elif (not predicted) and expected:
            self.fn += 1
        else:
            self.tn += 1

    @property
    def support(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return (self.tp / denom) if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return (self.tp / denom) if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "support": self.support,
        }


@dataclass
class ComplianceMetrics:
    overall: Confusion = field(default_factory=Confusion)
    by_check_type: dict[str, Confusion] = field(default_factory=dict)
    severity_matches: int = 0
    severity_total: int = 0

    def observe(
        self,
        *,
        check_type: str,
        predicted_flag: bool,
        expected_flag: bool,
        predicted_severity: str | None = None,
        expected_severity: str | None = None,
    ) -> None:
        self.overall.add(predicted_flag, expected_flag)
        bucket = self.by_check_type.setdefault(check_type, Confusion())
        bucket.add(predicted_flag, expected_flag)
        if expected_flag and expected_severity:
            self.severity_total += 1
            if predicted_flag and (predicted_severity or "") == expected_severity:
                self.severity_matches += 1

    @property
    def severity_accuracy(self) -> float | None:
        if self.severity_total == 0:
            return None
        return self.severity_matches / self.severity_total

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall.as_dict(),
            "by_check_type": {
                name: conf.as_dict()
                for name, conf in sorted(self.by_check_type.items())
            },
            "severity_accuracy": (
                None
                if self.severity_accuracy is None
                else round(self.severity_accuracy, 4)
            ),
            "severity_matches": self.severity_matches,
            "severity_total": self.severity_total,
        }


@dataclass
class SegmentationMetrics:
    evaluated: int = 0
    within_tolerance: int = 0
    abs_errors: list[int] = field(default_factory=list)
    overlap_scores: list[float] = field(default_factory=list)
    skipped_cuad: int = 0

    def observe_count(
        self,
        *,
        predicted_count: int,
        expected_count: int,
        tolerance: int = 0,
    ) -> None:
        self.evaluated += 1
        err = abs(predicted_count - expected_count)
        self.abs_errors.append(err)
        if err <= tolerance:
            self.within_tolerance += 1

    def observe_overlap(self, score: float) -> None:
        self.overlap_scores.append(float(score))

    @property
    def accuracy(self) -> float:
        return (self.within_tolerance / self.evaluated) if self.evaluated else 0.0

    @property
    def mean_abs_error(self) -> float:
        if not self.abs_errors:
            return 0.0
        return sum(self.abs_errors) / len(self.abs_errors)

    @property
    def mean_overlap(self) -> float | None:
        if not self.overlap_scores:
            return None
        return sum(self.overlap_scores) / len(self.overlap_scores)

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "within_tolerance": self.within_tolerance,
            "accuracy": round(self.accuracy, 4),
            "mean_abs_error": round(self.mean_abs_error, 4),
            "mean_overlap": (
                None if self.mean_overlap is None else round(self.mean_overlap, 4)
            ),
            "skipped_cuad": self.skipped_cuad,
        }


@dataclass
class VerifierMetrics:
    findings_with_quote: int = 0
    quote_valid: int = 0
    verified_pass: int = 0
    verified_total: int = 0

    def observe_finding(
        self,
        *,
        has_quote: bool,
        quote_valid: bool,
        verified: bool | None = None,
    ) -> None:
        if has_quote:
            self.findings_with_quote += 1
            if quote_valid:
                self.quote_valid += 1
        if verified is not None:
            self.verified_total += 1
            if verified:
                self.verified_pass += 1

    @property
    def quote_valid_rate(self) -> float:
        if self.findings_with_quote == 0:
            return 0.0
        return self.quote_valid / self.findings_with_quote

    @property
    def verified_rate(self) -> float | None:
        if self.verified_total == 0:
            return None
        return self.verified_pass / self.verified_total

    def as_dict(self) -> dict[str, Any]:
        return {
            "findings_with_quote": self.findings_with_quote,
            "quote_valid": self.quote_valid,
            "quote_valid_rate": round(self.quote_valid_rate, 4),
            "verified_pass": self.verified_pass,
            "verified_total": self.verified_total,
            "verified_rate": (
                None if self.verified_rate is None else round(self.verified_rate, 4)
            ),
        }


def span_overlap_ratio(
    predicted: Sequence[tuple[int, int]],
    gold: Sequence[tuple[int, int]],
) -> float:
    """Simple character-overlap: mean best IoU of each gold span vs predicted."""
    if not gold:
        return 1.0 if not predicted else 0.0
    if not predicted:
        return 0.0

    scores: list[float] = []
    for g_start, g_end in gold:
        g_len = max(0, g_end - g_start)
        if g_len == 0:
            continue
        best = 0.0
        for p_start, p_end in predicted:
            inter = max(0, min(g_end, p_end) - max(g_start, p_start))
            union = max(g_end, p_end) - min(g_start, p_start)
            if union <= 0:
                continue
            best = max(best, inter / union)
        scores.append(best)
    return sum(scores) / len(scores) if scores else 0.0


def predicted_flag_map(
    findings: Iterable[dict[str, Any]],
    *,
    contract_id: str,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Map (contract_id, clause_id, check_type) → finding row (flagged only)."""
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for finding in findings:
        clause_id = str(finding.get("clause_id") or "")
        check_type = str(finding.get("check_type") or "")
        if not clause_id or not check_type:
            continue
        out[(contract_id, clause_id, check_type)] = finding
    return out
