"""Day 9 — MLflow logging for eval experiments (not model training)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

# Metric / param keys expected by Day 9 plan.
PARAM_KEYS = ("model", "top_k", "prompt_version", "check_types")
METRIC_KEYS = (
    "precision",
    "recall",
    "f1",
    "quote_valid_rate",
    "latency_p95",
)


def default_tracking_uri(root: Path | None = None) -> str:
    """SQLite store under ``mlruns/`` (gitignored; file store is deprecated)."""
    root = root or ROOT
    db_path = (root / "mlruns" / "tracking.db").resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # SQLAlchemy URLs need forward slashes on Windows.
    return f"sqlite:///{db_path.as_posix()}"


def normalize_tracking_uri(uri: str | None, *, root: Path | None = None) -> str:
    """Resolve config/CLI tracking URI to an MLflow-compatible string."""
    root = root or ROOT
    if not uri:
        return default_tracking_uri(root)
    text = str(uri).strip()
    if text.startswith(("sqlite:", "http://", "https://", "postgresql:")):
        return text
    if text.startswith("file:"):
        # Newer MLflow requires an explicit opt-in for filesystem stores.
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        return text
    # Bare path → SQLite DB inside that directory (or the path if it ends with .db).
    path = Path(text)
    if not path.is_absolute():
        path = (root / path).resolve()
    else:
        path = path.resolve()
    if path.suffix.lower() == ".db":
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}"
    path.mkdir(parents=True, exist_ok=True)
    db = path / "tracking.db"
    return f"sqlite:///{db.as_posix()}"


def resolve_eval_params(
    pipe_cfg: dict[str, Any],
    *,
    top_k: int | None = None,
    prompt_version: str | None = None,
    model: str | None = None,
    check_types: Iterable[str] | None = None,
) -> dict[str, str]:
    """Flatten pipeline + CLI overrides into MLflow string params."""
    compliance = dict(pipe_cfg.get("compliance") or {})
    from src.compliance.check_types import CHECK_TYPES

    resolved_top_k = top_k if top_k is not None else compliance.get("top_k", 5)
    resolved_model = model if model is not None else compliance.get("model", "gpt-4o-mini")
    resolved_prompt = (
        prompt_version
        if prompt_version is not None
        else compliance.get("prompt_version", "v1")
    )
    if check_types is None:
        check_types = [ct.value for ct in CHECK_TYPES]
    return {
        "model": str(resolved_model),
        "top_k": str(int(resolved_top_k)),
        "prompt_version": str(resolved_prompt),
        "check_types": ",".join(str(c) for c in check_types),
    }


def extract_eval_metrics(
    report: dict[str, Any],
    *,
    latency_p95_sec: float | None = None,
) -> dict[str, float]:
    """Pull Day 9 metrics from an eval report payload."""
    metrics: dict[str, float] = {}
    compliance_eval = report.get("compliance_eval") or {}
    overall = (compliance_eval.get("compliance") or {}).get("overall") or {}
    verifier = compliance_eval.get("verifier") or {}

    for key in ("precision", "recall", "f1"):
        value = overall.get(key)
        if isinstance(value, (int, float)):
            metrics[key] = float(value)

    qvr = verifier.get("quote_valid_rate")
    if isinstance(qvr, (int, float)):
        metrics["quote_valid_rate"] = float(qvr)

    latency = latency_p95_sec
    if latency is None:
        latency = (report.get("latency") or {}).get("p95_sec")
    if isinstance(latency, (int, float)):
        metrics["latency_p95"] = float(latency)

    return metrics


def collect_report_artifacts(
    runs: dict[str, dict[str, Any]],
    *,
    report_dir: Path | None = None,
    eval_json: Path | None = None,
) -> list[Path]:
    """Gather findings.json / audit_report.md (+ eval JSON) for MLflow."""
    paths: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path | None) -> None:
        if path is None:
            return
        path = Path(path)
        if not path.is_file():
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        paths.append(path)

    _add(eval_json)

    for contract_id, result in sorted(runs.items()):
        report = result.get("report") or {}
        for key in ("findings_json_path", "audit_report_path"):
            raw = report.get(key)
            if raw:
                _add(Path(str(raw)))
        if report_dir is not None:
            child = Path(report_dir) / str(contract_id)
            _add(child / "findings.json")
            _add(child / "audit_report.md")

    return paths


def write_run_findings_bundle(
    runs: dict[str, dict[str, Any]],
    dest: Path,
) -> Path:
    """Write a combined findings.json when per-doc reporter artifacts are absent."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "contracts": sorted(runs),
        "findings_by_contract": {
            cid: list(result.get("findings") or [])
            for cid, result in sorted(runs.items())
        },
    }
    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return dest


def log_eval_to_mlflow(
    *,
    report: dict[str, Any],
    params: dict[str, str],
    metrics: dict[str, float],
    artifact_paths: Iterable[Path],
    experiment_name: str,
    run_name: str | None = None,
    tags: dict[str, str] | None = None,
    tracking_uri: str | None = None,
    root: Path | None = None,
) -> str:
    """Start an MLflow run, log params/metrics/artifacts; return run_id."""
    import mlflow
    from mlflow.tracking import MlflowClient

    root = root or ROOT
    uri = normalize_tracking_uri(tracking_uri, root=root)
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=run_name) as active:
        run_id = active.info.run_id
        if tags:
            mlflow.set_tags({str(k): str(v) for k, v in tags.items()})
        for key, value in params.items():
            mlflow.log_param(key, value)
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                mlflow.log_metric(key, float(value))

        # Always persist the full eval report under artifacts/eval/
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_path = tmp_path / "eval_report.json"
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            mlflow.log_artifact(str(report_path), artifact_path="eval")

        for path in artifact_paths:
            path = Path(path)
            if not path.is_file():
                continue
            # Group by parent folder name when it looks like a doc_id dir.
            parent_name = path.parent.name
            if parent_name and parent_name not in (".", "tmp", "Temp"):
                artifact_subdir = f"reports/{parent_name}"
            else:
                artifact_subdir = "reports"
            mlflow.log_artifact(str(path), artifact_path=artifact_subdir)

        # Record tracking metadata on the client for compare_runs.
        client = MlflowClient(tracking_uri=uri)
        client.set_tag(run_id, "eval.mode", str(report.get("mode") or ""))
        return run_id
