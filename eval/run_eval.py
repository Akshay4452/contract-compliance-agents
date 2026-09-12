#!/usr/bin/env python3
"""Day 8–9 eval harness — golden metrics + optional MLflow logging.

Examples (from repo root):

  # Offline: CUAD segmentation + golden validation
  py -3 eval/run_eval.py

  # Offline harness check (perfect labels → F1=1.0; not a model baseline)
  py -3 eval/run_eval.py --oracle

  # Score existing Day 7 / LLM result artifacts
  py -3 eval/run_eval.py --predictions-dir data/exercises/day7_reporter

  # Live pipeline on all golden contracts (needs OPENAI_API_KEY + Chroma)
  py -3 eval/run_eval.py --live --auto-approve

  # Day 9 — log an oracle run to local MLflow (./mlruns)
  py -3 eval/run_eval.py --oracle --mlflow --run-name oracle_topk5 --top-k 5

  # Validate golden clause ids against the segmenter
  py -3 eval/run_eval.py --validate-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.golden import (  # noqa: E402
    load_contracts_index,
    load_golden_cases,
    validate_golden_against_segmenter,
)
from eval.metrics import fmt_rate, latency_p95  # noqa: E402
from eval.mlflow_tracking import (  # noqa: E402
    collect_report_artifacts,
    extract_eval_metrics,
    log_eval_to_mlflow,
    normalize_tracking_uri,
    resolve_eval_params,
    write_run_findings_bundle,
)
from eval.scoring import (  # noqa: E402
    build_oracle_runs,
    enrich_runs_with_clause_text,
    load_predictions_dir,
    score_runs,
)
from eval.segmentation import run_segmentation_eval  # noqa: E402


def _load_pipeline_yaml() -> dict[str, Any]:
    path = ROOT / "config" / "pipeline.yaml"
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

def _print_compliance(block: dict[str, Any]) -> None:
    overall = block.get("overall") or {}
    print("--- Compliance (golden expected_flag) ---")
    print(
        f"  support={overall.get('support')}  "
        f"tp={overall.get('tp')} fp={overall.get('fp')} "
        f"tn={overall.get('tn')} fn={overall.get('fn')}"
    )
    print(
        f"  precision={fmt_rate(overall.get('precision'))}  "
        f"recall={fmt_rate(overall.get('recall'))}  "
        f"f1={fmt_rate(overall.get('f1'))}"
    )
    sev = block.get("severity_accuracy")
    print(
        f"  severity_accuracy={fmt_rate(sev)}  "
        f"(compared={block.get('severity_compared')})"
    )
    by_ct = block.get("by_check_type") or {}
    if by_ct:
        print("  by check_type:")
        for name, row in by_ct.items():
            print(
                f"    {name:28}  "
                f"P={fmt_rate(row.get('precision'))}  "
                f"R={fmt_rate(row.get('recall'))}  "
                f"F1={fmt_rate(row.get('f1'))}  "
                f"n={row.get('support')}"
            )


def _print_verifier(block: dict[str, Any]) -> None:
    print("--- Verifier (quote grounding) ---")
    print(
        f"  findings={block.get('findings')}  "
        f"quote_valid={block.get('quote_valid')}  "
        f"quote_valid_rate={fmt_rate(block.get('quote_valid_rate'))}"
    )


def _print_segmentation(block: dict[str, Any]) -> None:
    print("--- Segmentation (CUAD spans) ---")
    status = block.get("status")
    if status != "ok":
        print(f"  status={status}  reason={block.get('reason')}")
        return
    print(
        f"  documents={block.get('document_count')}  "
        f"clause_count_within_tol="
        f"{fmt_rate(block.get('clause_count_within_tolerance_rate'))}  "
        f"(tol={block.get('clause_count_tolerance')})"
    )
    print(
        f"  mean_max_iou={fmt_rate(block.get('mean_max_iou'))}  "
        f"mean_hit@iou>=0.1="
        f"{fmt_rate(block.get('mean_gold_span_hit_rate_iou_0_1'))}"
    )
    for doc in block.get("documents") or []:
        print(
            f"    {doc.get('document_id')}: "
            f"pred={doc.get('pred_clause_count')} "
            f"gold_spans={doc.get('gold_span_count')} "
            f"iou={fmt_rate(doc.get('mean_max_iou'))} "
            f"count_ok={doc.get('clause_count_within_tolerance')}"
        )


def run_live(
    contracts: dict[str, Path],
    contract_ids: list[str],
    *,
    top_k: int | None,
    max_clauses: int | None,
    min_confidence: float | None,
    auto_approve: bool,
    out_dir: Path,
) -> tuple[dict[str, dict[str, Any]], list[float]]:
    from src.graph.pipeline import run_contract

    runs: dict[str, dict[str, Any]] = {}
    latencies: list[float] = []
    for contract_id in contract_ids:
        path = contracts[contract_id]
        print(f"  live: {contract_id} <- {path}")
        t0 = time.perf_counter()
        result = run_contract(
            path,
            max_clauses=max_clauses,
            top_k=top_k,
            min_confidence=min_confidence,
            auto_approve=auto_approve,
            out_dir=out_dir,
            write_report=True,
        )
        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)
        print(
            f"    clauses={len(result.get('clauses') or [])}  "
            f"findings={len(result.get('findings') or [])}  "
            f"verified={len(result.get('verified_findings') or [])}  "
            f"{elapsed:.1f}s"
        )
        runs[contract_id] = result
    return runs, latencies


def _maybe_log_mlflow(
    *,
    enabled: bool,
    report: dict[str, Any],
    runs: dict[str, dict[str, Any]],
    pipe_cfg: dict[str, Any],
    mlflow_cfg: dict[str, Any],
    args: argparse.Namespace,
    latencies: list[float],
) -> str | None:
    if not enabled:
        return None

    params = resolve_eval_params(
        pipe_cfg,
        top_k=args.top_k,
        prompt_version=args.prompt_version,
    )
    p95 = latency_p95(latencies)
    metrics = extract_eval_metrics(report, latency_p95_sec=p95)

    artifact_paths = collect_report_artifacts(
        runs,
        report_dir=args.report_dir,
        eval_json=args.out,
    )
    # Oracle / predictions often lack Day 7 reporter files — still log findings.
    has_findings_artifact = any(p.name == "findings.json" for p in artifact_paths)
    if runs and not has_findings_artifact:
        bundle = args.report_dir / "_mlflow_bundle" / "findings.json"
        write_run_findings_bundle(runs, bundle)
        artifact_paths.append(bundle)

    tracking_uri = normalize_tracking_uri(
        args.tracking_uri or mlflow_cfg.get("tracking_uri"),
        root=ROOT,
    )

    experiment = args.experiment or str(
        mlflow_cfg.get("experiment_name", "contract-compliance-eval")
    )
    tags = {"eval.mode": str(report.get("mode") or "")}
    if args.mlflow_tag:
        for item in args.mlflow_tag:
            if "=" in item:
                key, value = item.split("=", 1)
                tags[key.strip()] = value.strip()

    try:
        run_id = log_eval_to_mlflow(
            report=report,
            params=params,
            metrics=metrics,
            artifact_paths=artifact_paths,
            experiment_name=experiment,
            run_name=args.run_name,
            tags=tags,
            tracking_uri=tracking_uri,
            root=ROOT,
        )
    except ModuleNotFoundError as exc:
        print(
            f"MLflow logging failed: missing dependency ({exc.name}). "
            "Install requirements.txt."
        )
        return None

    print(
        f"mlflow: experiment={experiment}  run_id={run_id}  "
        f"params={params}  metrics={{{', '.join(f'{k}={fmt_rate(v)}' for k, v in metrics.items())}}}"
    )
    return run_id

def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    pipe_cfg = _load_pipeline_yaml()
    eval_cfg = dict(pipe_cfg.get("eval") or {})
    mlflow_cfg = dict(pipe_cfg.get("mlflow") or {})

    parser = argparse.ArgumentParser(
        description="Day 8–9 golden eval + CUAD segmentation + optional MLflow",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / str(eval_cfg.get("golden_path", "data/golden/compliance_cases.jsonl")),
        help="Path to compliance_cases.jsonl",
    )
    parser.add_argument(
        "--contracts-index",
        type=Path,
        default=ROOT
        / str(eval_cfg.get("contracts_index", "data/golden/contracts_index.yaml")),
        help="YAML map of contract_id → .txt path",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--live",
        action="store_true",
        help="Run the LangGraph pipeline on golden contracts",
    )
    mode.add_argument(
        "--oracle",
        action="store_true",
        help="Score perfect golden-derived predictions (offline harness check)",
    )
    mode.add_argument(
        "--predictions-dir",
        type=Path,
        default=None,
        help="Score existing findings.json / *_llm_results.json",
    )
    parser.add_argument(
        "--contract-id",
        action="append",
        default=None,
        help="Limit to one or more contract_ids (repeatable)",
    )
    parser.add_argument(
        "--skip-segmentation",
        action="store_true",
        help="Skip CUAD segmentation metrics",
    )
    parser.add_argument(
        "--cuad-limit",
        type=int,
        default=int(eval_cfg.get("cuad_limit", 5)),
        help="How many CUAD contracts to score for segmentation",
    )
    parser.add_argument(
        "--clause-count-tolerance",
        type=float,
        default=float(eval_cfg.get("clause_count_tolerance", 0.25)),
        help="Relative error allowed for pred vs gold span counts",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only check golden clause_ids against the segmenter",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="With --live, set reporter human gate to approved",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override RAG top_k for --live (also logged to MLflow)",
    )
    parser.add_argument(
        "--max-clauses",
        type=int,
        default=None,
        help="Cap clauses for --live (cost control)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Override verifier min_confidence for --live",
    )
    parser.add_argument(
        "--prompt-version",
        default=None,
        help="Prompt version tag for MLflow (default: compliance.prompt_version)",
    )
    parser.add_argument(
        "--mlflow",
        action="store_true",
        help="Log params/metrics/artifacts to local MLflow (./mlruns)",
    )
    parser.add_argument(
        "--experiment",
        default=None,
        help="MLflow experiment name",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional MLflow run name",
    )
    parser.add_argument(
        "--tracking-uri",
        default=None,
        help="Override MLflow tracking URI",
    )
    parser.add_argument(
        "--mlflow-tag",
        action="append",
        default=None,
        help="Extra MLflow tag as key=value (repeatable)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT
        / str(eval_cfg.get("output_json", "data/exercises/day8_eval/last_eval.json")),
        help="Where to write the JSON metrics report",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT
        / str(eval_cfg.get("report_dir", "data/exercises/day8_eval/reports")),
        help="Day 7-style report parent dir for --live runs",
    )
    args = parser.parse_args(argv)

    cases = load_golden_cases(args.golden)
    contracts = load_contracts_index(args.contracts_index, root=ROOT)

    print(f"golden_cases={len(cases)}  contracts_indexed={len(contracts)}")

    problems = validate_golden_against_segmenter(cases, contracts)
    if problems:
        print(f"golden validation FAILED ({len(problems)} issues):")
        for msg in problems[:20]:
            print(f"  - {msg}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        return 1
    print("golden validation: ok (clause_ids match segmenter)")

    if args.validate_only:
        return 0

    if args.live:
        mode_name = "live"
    elif args.oracle:
        mode_name = "oracle"
    elif args.predictions_dir:
        mode_name = "predictions"
    else:
        mode_name = "segmentation_only"

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode_name,
        "golden_path": str(args.golden),
        "golden_case_count": len(cases),
    }

    # --- Compliance + verifier ---
    runs: dict[str, dict[str, Any]] = {}
    latencies: list[float] = []
    if args.live:
        wanted = args.contract_id or sorted(contracts)
        missing = [c for c in wanted if c not in contracts]
        if missing:
            print(f"unknown contract_id(s): {missing}")
            return 1
        print(f"running live pipeline on {len(wanted)} contract(s)...")
        args.report_dir.mkdir(parents=True, exist_ok=True)
        try:
            runs, latencies = run_live(
                contracts,
                wanted,
                top_k=args.top_k,
                max_clauses=args.max_clauses,
                min_confidence=args.min_confidence,
                auto_approve=args.auto_approve,
                out_dir=args.report_dir,
            )
        except ModuleNotFoundError as exc:
            print(
                f"live mode failed: missing dependency ({exc.name}). "
                "Install requirements.txt, or use --oracle / --predictions-dir."
            )
            return 1
    elif args.oracle:
        wanted = args.contract_id or sorted(contracts)
        print(f"building oracle predictions for {len(wanted)} contract(s)...")
        t0 = time.perf_counter()
        runs = build_oracle_runs(cases, contracts, contract_ids=wanted)
        # Attribute wall time evenly so latency_p95 is defined offline.
        elapsed = time.perf_counter() - t0
        if wanted:
            per = elapsed / len(wanted)
            latencies = [per] * len(wanted)
        else:
            latencies = [elapsed]
    elif args.predictions_dir:
        pred_dir = args.predictions_dir
        if not pred_dir.is_absolute():
            pred_dir = ROOT / pred_dir
        print(f"loading predictions from {pred_dir}")
        runs = load_predictions_dir(pred_dir)
        runs = enrich_runs_with_clause_text(runs, contracts)
        if args.contract_id:
            runs = {k: v for k, v in runs.items() if k in set(args.contract_id)}
        print(f"  loaded {len(runs)} contract prediction set(s)")

    if latencies:
        p95 = latency_p95(latencies)
        report["latency"] = {
            "per_contract_sec": [round(x, 4) for x in latencies],
            "p95_sec": p95,
            "count": len(latencies),
        }
        print(
            f"--- Latency ---\n  n={len(latencies)}  "
            f"p95={fmt_rate(p95)}s"
        )

    if runs:
        fuzzy = bool((pipe_cfg.get("verifier") or {}).get("fuzzy_quote", True))
        scored = score_runs(cases, runs, fuzzy_quote=fuzzy)
        if args.oracle:
            scored["note"] = (
                "oracle mode uses golden labels as predictions — "
                "F1≈1.0 means the harness works, not that the model is good"
            )
        report["compliance_eval"] = scored
        _print_compliance(scored.get("compliance") or {})
        _print_verifier(scored.get("verifier") or {})
        if args.oracle:
            print("  note: oracle harness check (not a live model baseline)")
    else:
        print(
            "--- Compliance / verifier ---"
            "\n  skipped (pass --live, --oracle, or --predictions-dir)"
        )
        report["compliance_eval"] = {"status": "skipped"}

    # --- Segmentation ---
    if args.skip_segmentation:
        report["segmentation_eval"] = {"status": "skipped", "reason": "cli flag"}
        print("--- Segmentation ---\n  skipped")
    else:
        seg = run_segmentation_eval(
            root=ROOT,
            limit=args.cuad_limit,
            clause_count_tolerance=args.clause_count_tolerance,
        )
        report["segmentation_eval"] = seg
        _print_segmentation(seg)

    # Resolve params for the JSON report even without --mlflow.
    report["params"] = resolve_eval_params(
        pipe_cfg,
        top_k=args.top_k,
        prompt_version=args.prompt_version,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        rel = args.out.resolve().relative_to(ROOT.resolve())
    except ValueError:
        rel = args.out
    print(f"wrote {rel}")

    mlflow_enabled = bool(args.mlflow or mlflow_cfg.get("enabled"))
    if mlflow_enabled and report["compliance_eval"].get("status") == "skipped":
        print("MLflow: skipped (no compliance metrics — use --oracle/--live/--predictions-dir)")
    elif mlflow_enabled:
        run_id = _maybe_log_mlflow(
            enabled=True,
            report=report,
            runs=runs,
            pipe_cfg=pipe_cfg,
            mlflow_cfg=mlflow_cfg,
            args=args,
            latencies=latencies,
        )
        if run_id:
            report["mlflow_run_id"] = run_id
            args.out.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
