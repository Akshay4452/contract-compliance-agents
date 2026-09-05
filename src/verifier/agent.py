"""Verifier agent: annotate findings; keep only grounded ones."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from src.verifier.corpus import (
    CorpusCatalog,
    cached_corpus_catalog,
    load_corpus_catalog,
)
from src.verifier.rules import (
    confidence_ok,
    quote_in_clause,
    regulation_ref_known,
)

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def load_pipeline_config(root: Path | None = None) -> dict[str, Any]:
    root = root or ROOT
    path = root / "config" / "pipeline.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _verifier_cfg(root: Path | None = None) -> dict[str, Any]:
    return dict(load_pipeline_config(root).get("verifier") or {})


def _clause_map(clauses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(c.get("id") or ""): c for c in clauses if c.get("id") is not None}


def verify_finding(
    finding: dict[str, Any],
    *,
    clause_text: str | None,
    catalog: CorpusCatalog,
    min_confidence: float = 0.5,
    fuzzy_quote: bool = True,
) -> dict[str, Any]:
    """Return a copy of ``finding`` with ``verified`` / ``reject_reason`` set."""
    out = dict(finding)
    quote = str(out.get("evidence_quote") or "").strip()
    ref = str(out.get("regulation_ref") or "").strip()
    conf = out.get("confidence")

    if clause_text is None:
        out["verified"] = False
        out["reject_reason"] = "missing_clause"
        return out

    if not quote:
        out["verified"] = False
        out["reject_reason"] = "missing_evidence_quote"
        return out

    if not quote_in_clause(quote, clause_text, fuzzy=fuzzy_quote):
        out["verified"] = False
        out["reject_reason"] = "quote_not_in_clause"
        return out

    if not ref:
        out["verified"] = False
        out["reject_reason"] = "missing_regulation_ref"
        return out

    if not regulation_ref_known(ref, catalog):
        out["verified"] = False
        out["reject_reason"] = "regulation_ref_not_in_corpus"
        return out

    if not confidence_ok(conf if isinstance(conf, (int, float)) else None, min_confidence):
        out["verified"] = False
        out["reject_reason"] = "confidence_below_threshold"
        return out

    out["verified"] = True
    out["reject_reason"] = ""
    return out


def run_verifier(
    findings: list[dict[str, Any]],
    clauses: list[dict[str, Any]],
    *,
    catalog: CorpusCatalog | None = None,
    min_confidence: float | None = None,
    fuzzy_quote: bool | None = None,
    root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Annotate all findings; return ``(annotated_all, verified_only)``."""
    root = root or ROOT
    cfg = _verifier_cfg(root)
    min_conf = float(
        min_confidence if min_confidence is not None else cfg.get("min_confidence", 0.5)
    )
    fuzzy = (
        bool(fuzzy_quote)
        if fuzzy_quote is not None
        else bool(cfg.get("fuzzy_quote", True))
    )

    if catalog is None:
        catalog = cached_corpus_catalog(str(root.resolve()))

    by_id = _clause_map(clauses)
    annotated: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []

    for finding in findings:
        clause_id = str(finding.get("clause_id") or "")
        clause = by_id.get(clause_id)
        clause_text = None if clause is None else str(clause.get("text") or "")
        row = verify_finding(
            finding,
            clause_text=clause_text,
            catalog=catalog,
            min_confidence=min_conf,
            fuzzy_quote=fuzzy,
        )
        annotated.append(row)
        if row.get("verified"):
            verified.append(row)
        else:
            logger.info(
                "reject finding_id=%s reason=%s",
                row.get("finding_id"),
                row.get("reject_reason"),
            )

    return annotated, verified


def get_default_catalog(root: Path | None = None) -> CorpusCatalog:
    """Public helper for tests / scripts."""
    return load_corpus_catalog(root or ROOT)
