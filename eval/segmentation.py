"""CUAD segmentation metrics: clause-count tolerance + span overlap."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.segmenter.models import Clause
from src.segmenter.splitter import segment_text
from src.segmenter.store import document_id_from_path

ROOT = Path(__file__).resolve().parents[1]
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Span:
    start: int
    end: int

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")


def load_cuad_config(root: Path | None = None) -> dict[str, Path]:
    root = root or ROOT
    with (root / "config" / "data_paths.yaml").open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["cuad"]

    def resolve(key: str) -> Path:
        p = Path(cfg[key])
        return p if p.is_absolute() else root / p

    return {
        "contracts_txt_dir": resolve("contracts_txt_dir"),
        "squad_json": resolve("squad_json"),
    }


def clause_span(clause: Clause | dict[str, Any]) -> Span:
    if isinstance(clause, Clause):
        start = int(clause.start_hint)
        text = clause.text
    else:
        start = int(clause.get("start_hint") or 0)
        text = str(clause.get("text") or "")
    return Span(start=start, end=start + len(text))


def span_iou(a: Span, b: Span) -> float:
    inter = max(0, min(a.end, b.end) - max(a.start, b.start))
    union = a.length + b.length - inter
    if union <= 0:
        return 0.0
    return inter / union


def gold_spans_for_context(context: str, answers: list[dict]) -> list[Span]:
    """Build unique labeled spans from SQuAD-style answers."""
    seen: set[tuple[int, int]] = set()
    spans: list[Span] = []
    for ans in answers:
        text = str(ans.get("text") or "")
        start = ans.get("answer_start")
        if start is None or not text:
            continue
        start_i = int(start)
        end_i = start_i + len(text)
        # Prefer exact offsets; fall back to find() when context drifted.
        if context[start_i:end_i] != text:
            found = context.find(text)
            if found < 0:
                continue
            start_i, end_i = found, found + len(text)
        key = (start_i, end_i)
        if key in seen:
            continue
        seen.add(key)
        spans.append(Span(start=start_i, end=end_i))
    return spans


def load_cuad_gold_spans(
    squad_path: Path,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load CUAD contracts with labeled answer spans.

    Returns list of ``{title, slug, context, spans}``.
    """
    payload = json.loads(squad_path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for item in payload.get("data") or []:
        title = str(item.get("title") or "")
        paragraphs = item.get("paragraphs") or []
        if not paragraphs:
            continue
        # CUAD stores one giant paragraph per contract.
        context = str(paragraphs[0].get("context") or "")
        answers: list[dict] = []
        for qa in paragraphs[0].get("qas") or []:
            answers.extend(qa.get("answers") or [])
        spans = gold_spans_for_context(context, answers)
        if not spans:
            continue
        out.append(
            {
                "title": title,
                "slug": _slug(title),
                "context": context,
                "spans": spans,
            }
        )
        if limit is not None and len(out) >= limit:
            break
    return out


def match_contract_file(
    slug: str,
    contracts_dir: Path,
) -> Path | None:
    """Best-effort match of CUAD title slug to a ``.txt`` filename."""
    files = sorted(contracts_dir.glob("*.txt"))
    # Exact slug match on stem
    for path in files:
        if document_id_from_path(path) == slug or _slug(path.stem) == slug:
            return path
    # Prefix / containment (CUAD titles sometimes omit extensions / punctuation)
    for path in files:
        stem_slug = _slug(path.stem)
        if slug in stem_slug or stem_slug in slug:
            return path
    return None


def score_document_segmentation(
    *,
    pred_clauses: list[Clause] | list[dict[str, Any]],
    gold_spans: list[Span],
    clause_count_tolerance: float = 0.25,
) -> dict[str, Any]:
    """Clause-count tolerance + mean max-IoU of gold spans vs predicted clauses."""
    pred_spans = [clause_span(c) for c in pred_clauses]
    gold_n = len(gold_spans)
    pred_n = len(pred_spans)

    if gold_n == 0:
        count_ok = pred_n == 0
        relative_error = 0.0 if pred_n == 0 else 1.0
    else:
        relative_error = abs(pred_n - gold_n) / gold_n
        count_ok = relative_error <= clause_count_tolerance

    ious: list[float] = []
    hit_at_0_1 = 0
    for g in gold_spans:
        best = max((span_iou(g, p) for p in pred_spans), default=0.0)
        ious.append(best)
        if best >= 0.1:
            hit_at_0_1 += 1

    mean_iou = (sum(ious) / len(ious)) if ious else None
    recall_at_0_1 = (hit_at_0_1 / gold_n) if gold_n else None

    return {
        "pred_clause_count": pred_n,
        "gold_span_count": gold_n,
        "clause_count_relative_error": relative_error,
        "clause_count_within_tolerance": count_ok,
        "mean_max_iou": mean_iou,
        "gold_span_hit_rate_iou_0_1": recall_at_0_1,
    }


def run_segmentation_eval(
    *,
    root: Path | None = None,
    limit: int = 5,
    clause_count_tolerance: float = 0.25,
    prefer_txt_files: bool = True,
) -> dict[str, Any]:
    """Evaluate segmenter on the first ``limit`` CUAD contracts with gold spans."""
    root = root or ROOT
    paths = load_cuad_config(root)
    squad_path = paths["squad_json"]
    txt_dir = paths["contracts_txt_dir"]

    if not squad_path.is_file():
        return {
            "status": "skipped",
            "reason": f"missing CUAD squad json: {squad_path}",
            "documents": [],
        }
    if prefer_txt_files and not txt_dir.is_dir():
        return {
            "status": "skipped",
            "reason": f"missing CUAD txt dir: {txt_dir}",
            "documents": [],
        }

    gold_docs = load_cuad_gold_spans(squad_path, limit=None)
    # Prefer docs that have a matching .txt on disk, in sorted file order.
    docs: list[dict[str, Any]] = []
    if prefer_txt_files:
        for path in sorted(txt_dir.glob("*.txt")):
            stem_slug = document_id_from_path(path)
            match = next(
                (
                    g
                    for g in gold_docs
                    if g["slug"] == stem_slug
                    or g["slug"] in stem_slug
                    or stem_slug in g["slug"]
                ),
                None,
            )
            if match is None:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            # Prefer segmenting the on-disk txt (pipeline input); gold spans
            # come from SQuAD context which should be the same contract text.
            clauses = segment_text(text)
            # If txt and SQuAD context lengths diverge a lot, segment SQuAD
            # context so IoU remains meaningful.
            if abs(len(text) - len(match["context"])) > max(200, 0.05 * len(match["context"])):
                clauses = segment_text(match["context"])
                source = "squad_context"
            else:
                source = str(path)
            row = score_document_segmentation(
                pred_clauses=clauses,
                gold_spans=match["spans"],
                clause_count_tolerance=clause_count_tolerance,
            )
            row.update(
                {
                    "document_id": stem_slug,
                    "cuad_title": match["title"],
                    "source": source,
                }
            )
            docs.append(row)
            if len(docs) >= limit:
                break
    else:
        for match in gold_docs[:limit]:
            clauses = segment_text(match["context"])
            row = score_document_segmentation(
                pred_clauses=clauses,
                gold_spans=match["spans"],
                clause_count_tolerance=clause_count_tolerance,
            )
            row.update(
                {
                    "document_id": match["slug"],
                    "cuad_title": match["title"],
                    "source": "squad_context",
                }
            )
            docs.append(row)

    if not docs:
        return {
            "status": "skipped",
            "reason": "no CUAD documents matched for segmentation eval",
            "documents": [],
        }

    mean_iou_vals = [d["mean_max_iou"] for d in docs if d["mean_max_iou"] is not None]
    hit_vals = [
        d["gold_span_hit_rate_iou_0_1"]
        for d in docs
        if d["gold_span_hit_rate_iou_0_1"] is not None
    ]
    within = sum(1 for d in docs if d["clause_count_within_tolerance"])

    return {
        "status": "ok",
        "document_count": len(docs),
        "clause_count_tolerance": clause_count_tolerance,
        "clause_count_within_tolerance_rate": within / len(docs),
        "mean_max_iou": (sum(mean_iou_vals) / len(mean_iou_vals)) if mean_iou_vals else None,
        "mean_gold_span_hit_rate_iou_0_1": (sum(hit_vals) / len(hit_vals)) if hit_vals else None,
        "documents": docs,
    }
