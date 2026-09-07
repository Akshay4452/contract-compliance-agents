"""Day 8 eval harness: golden set → segmentation / compliance / verifier scores.

Usage:
  python eval/run_eval.py
  python eval/run_eval.py --mode offline --hallucinate-every 5
  python eval/run_eval.py --mode live --max-clauses 4
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.golden import (  # noqa: E402
    ComplianceCase,
    load_compliance_cases,
    load_segmentation_cases,
    list_contract_ids,
)
from eval.metrics import (  # noqa: E402
    ComplianceMetrics,
    SegmentationMetrics,
    VerifierMetrics,
    predicted_flag_map,
    span_overlap_ratio,
)
from eval.predictions import (  # noqa: E402
    quote_validity_for_findings,
    run_live_contract,
    run_offline_contract,
    segment_contract,
)

DEFAULT_OUT = ROOT / "data" / "golden" / "baseline_results.json"


def _score_compliance(
    cases: list[ComplianceCase],
    predictions_by_contract: dict[str, dict[str, Any]],
) -> ComplianceMetrics:
    metrics = ComplianceMetrics()
    for case in cases:
        pred_map = predicted_flag_map(
            predictions_by_contract.get(case.contract_id, {}).get("findings") or [],
            contract_id=case.contract_id,
        )
        finding = pred_map.get(case.key)
        predicted_flag = finding is not None
        predicted_severity = None if finding is None else finding.get("severity")
        metrics.observe(
            check_type=case.check_type,
            predicted_flag=predicted_flag,
            expected_flag=case.expected_flag,
            predicted_severity=(
                None if predicted_severity is None else str(predicted_severity)
            ),
            expected_severity=case.expected_severity,
        )
    return metrics


def _score_verifier(
    predictions_by_contract: dict[str, dict[str, Any]],
) -> VerifierMetrics:
    metrics = VerifierMetrics()
    for payload in predictions_by_contract.values():
        findings = payload.get("findings") or []
        clauses = payload.get("clauses") or []
        for finding, valid in quote_validity_for_findings(findings, clauses):
            quote = str(finding.get("evidence_quote") or "").strip()
            verified = finding.get("verified")
            metrics.observe_finding(
                has_quote=bool(quote),
                quote_valid=valid,
                verified=verified if isinstance(verified, bool) else None,
            )
    return metrics


def _score_segmentation_synthetic() -> SegmentationMetrics:
    metrics = SegmentationMetrics()
    for case in load_segmentation_cases():
        clauses = segment_contract(case.contract_id)
        metrics.observe_count(
            predicted_count=len(clauses),
            expected_count=case.expected_clause_count,
            tolerance=case.tolerance,
        )
        # Synthetic gold: treat each predicted clause span as self-overlap = 1.0
        # when count matches; otherwise partial credit via count error only.
        if abs(len(clauses) - case.expected_clause_count) <= case.tolerance:
            metrics.observe_overlap(1.0)
        else:
            # Soft overlap proxy from relative count error
            denom = max(case.expected_clause_count, 1)
            metrics.observe_overlap(
                max(0.0, 1.0 - abs(len(clauses) - case.expected_clause_count) / denom)
            )
    return metrics


def _score_segmentation_cuad(
    *,
    max_docs: int = 5,
    count_tolerance: int = 3,
) -> SegmentationMetrics:
    """Optional CUAD span overlap when local CUAD v1 is installed."""
    import yaml

    from src.segmenter.splitter import segment_text

    metrics = SegmentationMetrics()
    cfg_path = ROOT / "config" / "data_paths.yaml"
    with cfg_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["cuad"]
    txt_dir = Path(cfg["contracts_txt_dir"])
    squad_path = Path(cfg["squad_json"])
    if not txt_dir.is_dir() or not squad_path.is_file():
        metrics.skipped_cuad = 1
        return metrics

    with squad_path.open(encoding="utf-8") as fh:
        squad = json.load(fh)

    # Map title/filename stubs → answer character spans (simple concat context)
    evaluated = 0
    for doc in squad.get("data") or []:
        if evaluated >= max_docs:
            break
        title = str(doc.get("title") or "")
        # Find a matching txt by substring of title tokens
        matches = sorted(txt_dir.glob("*.txt"))
        contract_file = None
        needle = title.replace(" ", "")[:40].lower()
        for path in matches:
            if needle and needle in path.name.replace(" ", "").lower():
                contract_file = path
                break
        if contract_file is None:
            continue

        text = contract_file.read_text(encoding="utf-8", errors="replace")
        clauses = segment_text(text)
        predicted_spans = [
            (c.start_hint, c.start_hint + len(c.text)) for c in clauses
        ]

        gold_spans: list[tuple[int, int]] = []
        for para in doc.get("paragraphs") or []:
            context = str(para.get("context") or "")
            # Prefer offsets into the full contract text when context is a substring
            base = text.find(context) if context and context in text else 0
            for qa in para.get("qas") or []:
                for ans in qa.get("answers") or []:
                    start = int(ans.get("answer_start") or 0) + base
                    ans_text = str(ans.get("text") or "")
                    if not ans_text:
                        continue
                    gold_spans.append((start, start + len(ans_text)))

        if not gold_spans:
            continue

        # Distinct-ish gold regions as a crude expected clause count proxy
        expected_count = max(1, min(len({s[0] // 200 for s in gold_spans}), 40))
        metrics.observe_count(
            predicted_count=len(clauses),
            expected_count=expected_count,
            tolerance=count_tolerance,
        )
        metrics.observe_overlap(span_overlap_ratio(predicted_spans, gold_spans))
        evaluated += 1

    if evaluated == 0:
        metrics.skipped_cuad = 1
    return metrics


def _print_baseline(report: dict[str, Any]) -> None:
    seg = report["metrics"]["segmentation"]
    comp = report["metrics"]["compliance"]["overall"]
    by_check = report["metrics"]["compliance"]["by_check_type"]
    ver = report["metrics"]["verifier"]

    print()
    print("=== Day 8 baseline scores ===")
    print(f"mode={report['mode']}  contracts={report['contract_count']}  "
          f"golden_rows={report['golden_row_count']}")
    print()
    print("Segmentation")
    print(
        f"  clause_count_accuracy={seg['accuracy']:.4f}  "
        f"within_tol={seg['within_tolerance']}/{seg['evaluated']}  "
        f"mae={seg['mean_abs_error']:.4f}  "
        f"mean_overlap={seg['mean_overlap']}"
    )
    if seg.get("skipped_cuad"):
        print("  cuad=skipped (local CUAD_v1 not found)")
    print()
    print("Compliance (expected_flag)")
    print(
        f"  precision={comp['precision']:.4f}  "
        f"recall={comp['recall']:.4f}  "
        f"f1={comp['f1']:.4f}  "
        f"tp={comp['tp']} fp={comp['fp']} tn={comp['tn']} fn={comp['fn']}"
    )
    sev = report["metrics"]["compliance"].get("severity_accuracy")
    if sev is not None:
        print(f"  severity_accuracy={sev:.4f}")
    for name, row in by_check.items():
        print(
            f"  - {name}: p={row['precision']:.3f} "
            f"r={row['recall']:.3f} f1={row['f1']:.3f} "
            f"(n={row['support']})"
        )
    print()
    print("Verifier")
    print(
        f"  quote_valid_rate={ver['quote_valid_rate']:.4f}  "
        f"({ver['quote_valid']}/{ver['findings_with_quote']} findings with quotes)"
    )
    if ver.get("verified_rate") is not None:
        print(
            f"  verified_rate={ver['verified_rate']:.4f}  "
            f"({ver['verified_pass']}/{ver['verified_total']})"
        )
    print()


def run_eval(
    *,
    mode: str = "offline",
    hallucinate_every_n: int = 0,
    max_clauses: int | None = None,
    top_k: int | None = None,
    include_cuad: bool = True,
    out_path: Path | None = None,
) -> dict[str, Any]:
    cases = load_compliance_cases()
    contract_ids = list_contract_ids()
    predictions: dict[str, dict[str, Any]] = {}

    for contract_id in contract_ids:
        if mode == "live":
            predictions[contract_id] = run_live_contract(
                contract_id,
                max_clauses=max_clauses,
                top_k=top_k,
            )
        else:
            predictions[contract_id] = run_offline_contract(
                contract_id,
                cases,
                hallucinate_every_n=hallucinate_every_n,
            )

    seg = _score_segmentation_synthetic()
    if include_cuad:
        cuad = _score_segmentation_cuad()
        if cuad.evaluated:
            # Merge CUAD docs into the same metric object for reporting
            for err in cuad.abs_errors:
                # already recorded inside cuad; copy summary fields
                pass
            seg.evaluated += cuad.evaluated
            seg.within_tolerance += cuad.within_tolerance
            seg.abs_errors.extend(cuad.abs_errors)
            seg.overlap_scores.extend(cuad.overlap_scores)
        else:
            seg.skipped_cuad = cuad.skipped_cuad

    compliance = _score_compliance(cases, predictions)
    verifier = _score_verifier(predictions)

    report: dict[str, Any] = {
        "status": "ok",
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_count": len(contract_ids),
        "golden_row_count": len(cases),
        "hallucinate_every_n": hallucinate_every_n if mode == "offline" else None,
        "metrics": {
            "segmentation": seg.as_dict(),
            "compliance": compliance.as_dict(),
            "verifier": verifier.as_dict(),
        },
        "contracts": {
            cid: {
                "clause_count": len(payload.get("clauses") or []),
                "finding_count": len(payload.get("findings") or []),
                "verified_count": len(payload.get("verified_findings") or []),
                "errors": payload.get("errors") or [],
            }
            for cid, payload in predictions.items()
        },
    }

    dest = out_path or DEFAULT_OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report["results_path"] = str(dest)
    _print_baseline(report)
    try:
        rel = dest.resolve().relative_to(ROOT.resolve())
    except ValueError:
        rel = dest
    print(f"wrote {rel}")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Day 8 golden-set eval harness (segmentation / compliance / verifier).",
    )
    parser.add_argument(
        "--mode",
        choices=("offline", "live"),
        default="offline",
        help="offline=script findings from golden (default); live=full LLM pipeline",
    )
    parser.add_argument(
        "--hallucinate-every",
        type=int,
        default=0,
        dest="hallucinate_every_n",
        help="Offline only: inject a bad quote on every Nth positive finding "
        "(exercises verifier quote_valid_rate). 0=disabled.",
    )
    parser.add_argument(
        "--max-clauses",
        type=int,
        default=None,
        help="Live only: limit compliance to first N clauses per contract",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Live only: override RAG top_k",
    )
    parser.add_argument(
        "--no-cuad",
        action="store_true",
        help="Skip optional CUAD span-overlap segmentation scoring",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Where to write baseline JSON (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args(argv)

    run_eval(
        mode=args.mode,
        hallucinate_every_n=args.hallucinate_every_n,
        max_clauses=args.max_clauses,
        top_k=args.top_k,
        include_cuad=not args.no_cuad,
        out_path=args.out,
    )


if __name__ == "__main__":
    main()
