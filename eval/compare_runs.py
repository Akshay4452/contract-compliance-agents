#!/usr/bin/env python3
"""Compare MLflow eval runs (e.g. prompt v1 vs v2, or different top_k).

Examples (from repo root):

  py -3 eval/compare_runs.py
  py -3 eval/compare_runs.py --experiment contract-compliance-eval
  py -3 eval/compare_runs.py --param prompt_version
  py -3 eval/compare_runs.py --run-ids <id1>,<id2>
  py -3 eval/compare_runs.py --max-runs 10 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.metrics import fmt_rate  # noqa: E402
from eval.mlflow_tracking import (  # noqa: E402
    METRIC_KEYS,
    PARAM_KEYS,
    normalize_tracking_uri,
)

COMPARE_METRICS = list(METRIC_KEYS)
COMPARE_PARAMS = list(PARAM_KEYS)


def _load_mlflow_cfg() -> dict[str, Any]:
    path = ROOT / "config" / "pipeline.yaml"
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(raw.get("mlflow") or {})


def _format_cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return fmt_rate(value)
    return str(value)


def fetch_runs(
    *,
    experiment_name: str,
    tracking_uri: str,
    run_ids: list[str] | None = None,
    max_runs: int = 20,
) -> list[dict[str, Any]]:
    """Load finished/running MLflow runs as flat dicts for comparison."""
    import mlflow
    from mlflow.tracking import MlflowClient

    uri = normalize_tracking_uri(tracking_uri, root=ROOT)
    mlflow.set_tracking_uri(uri)
    client = MlflowClient(tracking_uri=uri)
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        return []

    if run_ids:
        rows: list[dict[str, Any]] = []
        for run_id in run_ids:
            run = client.get_run(run_id)
            rows.append(_run_to_row(run))
        return rows

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=max_runs,
    )
    return [_run_to_row(run) for run in runs]


def _run_to_row(run: Any) -> dict[str, Any]:
    data = run.data
    info = run.info
    row: dict[str, Any] = {
        "run_id": info.run_id,
        "run_name": info.run_name or "",
        "status": info.status,
        "start_time": info.start_time,
    }
    for key in COMPARE_PARAMS:
        row[key] = data.params.get(key)
    for key in COMPARE_METRICS:
        raw = data.metrics.get(key)
        row[key] = float(raw) if raw is not None else None
    row["mode"] = data.tags.get("eval.mode") or data.tags.get("mlflow.runName") or ""
    return row


def group_by_param(rows: list[dict[str, Any]], param: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(param) or "(unset)")
        groups.setdefault(key, []).append(row)
    return groups


def print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No MLflow runs found.")
        return

    headers = ["run_name", "run_id_short", *COMPARE_PARAMS, *COMPARE_METRICS]
    display_rows: list[list[str]] = []
    for row in rows:
        display_rows.append(
            [
                _format_cell(row.get("run_name") or row.get("run_id", "")[:8]),
                _format_cell(str(row.get("run_id") or "")[:8]),
                *[_format_cell(row.get(k)) for k in COMPARE_PARAMS],
                *[_format_cell(row.get(k)) for k in COMPARE_METRICS],
            ]
        )

    widths = [len(h) for h in headers]
    for cells in display_rows:
        for i, cell in enumerate(cells):
            widths[i] = max(widths[i], len(cell))

    def _line(cells: list[str]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))

    print(_line(headers))
    print(_line(["-" * w for w in widths]))
    for cells in display_rows:
        print(_line(cells))


def print_param_summary(rows: list[dict[str, Any]], param: str) -> None:
    groups = group_by_param(rows, param)
    print(f"\nGrouped by {param}:")
    for value, group in sorted(groups.items()):
        print(f"  {param}={value}  (n={len(group)})")
        for metric in COMPARE_METRICS:
            vals = [r[metric] for r in group if isinstance(r.get(metric), (int, float))]
            if not vals:
                continue
            mean = sum(vals) / len(vals)
            print(f"    {metric}: mean={fmt_rate(mean)}  latest={fmt_rate(vals[0])}")


def main(argv: list[str] | None = None) -> int:
    mlflow_cfg = _load_mlflow_cfg()
    parser = argparse.ArgumentParser(
        description="Compare Day 9 MLflow eval runs (prompt / top_k experiments)",
    )
    parser.add_argument(
        "--experiment",
        default=str(mlflow_cfg.get("experiment_name", "contract-compliance-eval")),
        help="MLflow experiment name",
    )
    parser.add_argument(
        "--tracking-uri",
        default=None,
        help="Override MLflow tracking URI (default: ./mlruns)",
    )
    parser.add_argument(
        "--run-ids",
        default=None,
        help="Comma-separated run ids to compare (optional)",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=20,
        help="Max recent runs when --run-ids is omitted",
    )
    parser.add_argument(
        "--param",
        default=None,
        choices=COMPARE_PARAMS,
        help="Also print a mean summary grouped by this param",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table",
    )
    args = parser.parse_args(argv)

    tracking_uri = normalize_tracking_uri(
        args.tracking_uri or mlflow_cfg.get("tracking_uri"),
        root=ROOT,
    )

    run_ids = None
    if args.run_ids:
        run_ids = [r.strip() for r in args.run_ids.split(",") if r.strip()]

    try:
        rows = fetch_runs(
            experiment_name=args.experiment,
            tracking_uri=tracking_uri,
            run_ids=run_ids,
            max_runs=args.max_runs,
        )
    except ModuleNotFoundError as exc:
        print(
            f"compare_runs failed: missing dependency ({exc.name}). "
            "Install requirements.txt (mlflow)."
        )
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"compare_runs failed: {exc}")
        return 1

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        print(f"experiment={args.experiment}")
        print(f"tracking_uri={tracking_uri}")
        print(f"runs={len(rows)}")
        print_table(rows)
        if args.param:
            print_param_summary(rows, args.param)
        elif rows:
            # Default: highlight prompt_version and top_k groupings when varied.
            for key in ("prompt_version", "top_k"):
                values = {str(r.get(key) or "") for r in rows}
                if len(values) > 1:
                    print_param_summary(rows, key)
                    break

    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
