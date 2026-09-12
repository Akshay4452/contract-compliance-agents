"""Unit tests for Day 8 eval harness (no LLM, no Chroma)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eval.golden import (
    load_contracts_index,
    load_golden_cases,
    validate_golden_against_segmenter,
)
from eval.metrics import Confusion, quote_valid_rate, score_compliance
from eval.scoring import score_runs
from eval.segmentation import Span, score_document_segmentation, span_iou

ROOT = Path(__file__).resolve().parents[1]


class MetricsTests(unittest.TestCase):
    def test_confusion_precision_recall_f1(self) -> None:
        c = Confusion()
        c.add(True, True)  # TP
        c.add(True, False)  # FN
        c.add(False, True)  # FP
        c.add(False, False)  # TN
        self.assertEqual(c.tp, 1)
        self.assertAlmostEqual(c.precision or 0, 0.5)
        self.assertAlmostEqual(c.recall or 0, 0.5)
        self.assertAlmostEqual(c.f1 or 0, 0.5)

    def test_score_compliance_keys(self) -> None:
        expected = [
            (("a", "c1", "subprocessor"), True, "high"),
            (("a", "c2", "subprocessor"), False, None),
            (("a", "c1", "data_retention"), True, "high"),
        ]
        predicted = {("a", "c1", "subprocessor"), ("a", "c2", "subprocessor")}
        metrics = score_compliance(
            expected_rows=expected,
            predicted_keys=predicted,
            predicted_severity={("a", "c1", "subprocessor"): "high"},
        )
        self.assertEqual(metrics.overall.tp, 1)
        self.assertEqual(metrics.overall.fp, 1)
        self.assertEqual(metrics.overall.fn, 1)
        self.assertEqual(metrics.overall.tn, 0)
        self.assertEqual(metrics.severity_matches, 1)
        self.assertEqual(metrics.severity_compared, 1)

    def test_quote_valid_rate(self) -> None:
        clauses = {"c1": "Vendor may share data without prior notice."}
        findings = [
            {"clause_id": "c1", "evidence_quote": "without prior notice"},
            {"clause_id": "c1", "evidence_quote": "hallucinated phrase"},
        ]
        result = quote_valid_rate(findings, clauses, fuzzy=True)
        self.assertEqual(result["findings"], 2)
        self.assertEqual(result["quote_valid"], 1)
        self.assertAlmostEqual(result["quote_valid_rate"] or 0, 0.5)


class SegmentationMetricTests(unittest.TestCase):
    def test_span_iou(self) -> None:
        a = Span(0, 100)
        b = Span(50, 150)
        self.assertAlmostEqual(span_iou(a, b), 50 / 150)

    def test_score_document_segmentation(self) -> None:
        pred = [
            {"id": "c1", "text": "x" * 80, "start_hint": 0},
            {"id": "c2", "text": "y" * 80, "start_hint": 100},
        ]
        gold = [Span(0, 70), Span(100, 160)]
        row = score_document_segmentation(
            pred_clauses=pred,
            gold_spans=gold,
            clause_count_tolerance=0.5,
        )
        self.assertTrue(row["clause_count_within_tolerance"])
        self.assertGreater(row["mean_max_iou"], 0.4)


class GoldenSetTests(unittest.TestCase):
    def test_golden_loads_and_validates(self) -> None:
        cases = load_golden_cases()
        self.assertGreaterEqual(len(cases), 40)
        self.assertLessEqual(len(cases), 60)
        contracts = load_contracts_index()
        problems = validate_golden_against_segmenter(cases, contracts)
        self.assertEqual(problems, [])

    def test_positive_and_negative_mix(self) -> None:
        cases = load_golden_cases()
        positives = sum(1 for c in cases if c.expected_flag)
        negatives = sum(1 for c in cases if not c.expected_flag)
        self.assertGreaterEqual(positives, 10)
        self.assertGreaterEqual(negatives, 20)


class ScoreRunsTests(unittest.TestCase):
    def test_perfect_predictions(self) -> None:
        cases = load_golden_cases()
        # Build oracle findings only for expected_flag=true rows.
        runs: dict = {}
        for case in cases:
            run = runs.setdefault(
                case.contract_id,
                {"clauses": [], "findings": []},
            )
            # Ensure clause text exists for quote checks.
            if not any(c["id"] == case.clause_id for c in run["clauses"]):
                run["clauses"].append(
                    {
                        "id": case.clause_id,
                        "text": f"Clause {case.clause_id} contains evidence token UNIQUE_{case.clause_id}.",
                    }
                )
            if case.expected_flag:
                clause_text = next(
                    c["text"] for c in run["clauses"] if c["id"] == case.clause_id
                )
                run["findings"].append(
                    {
                        "clause_id": case.clause_id,
                        "check_type": case.check_type,
                        "severity": case.expected_severity or "high",
                        "evidence_quote": f"UNIQUE_{case.clause_id}",
                        "issue": case.notes,
                    }
                )
                self.assertIn(f"UNIQUE_{case.clause_id}", clause_text)

        scored = score_runs(cases, runs, fuzzy_quote=True)
        overall = scored["compliance"]["overall"]
        self.assertEqual(overall["fp"], 0)
        self.assertEqual(overall["fn"], 0)
        self.assertEqual(overall["precision"], 1.0)
        self.assertEqual(overall["recall"], 1.0)
        self.assertEqual(scored["verifier"]["quote_valid_rate"], 1.0)


class CliSmokeTests(unittest.TestCase):
    def test_validate_only_exit_zero(self) -> None:
        from eval.run_eval import main

        code = main(["--validate-only", "--skip-segmentation"])
        self.assertEqual(code, 0)

    def test_oracle_scores_perfect(self) -> None:
        from eval.run_eval import main

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "eval.json"
            code = main(
                [
                    "--oracle",
                    "--skip-segmentation",
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["mode"], "oracle")
            overall = payload["compliance_eval"]["compliance"]["overall"]
            self.assertEqual(overall["fp"], 0)
            self.assertEqual(overall["fn"], 0)
            self.assertEqual(overall["f1"], 1.0)
            self.assertEqual(
                payload["compliance_eval"]["verifier"]["quote_valid_rate"],
                1.0,
            )

    def test_segmentation_writes_report(self) -> None:
        from eval.run_eval import main

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "eval.json"
            code = main(
                [
                    "--skip-segmentation",
                    "--out",
                    str(out),
                ]
            )
            # Without predictions, still writes a report.
            self.assertEqual(code, 0)
            self.assertTrue(out.is_file())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["compliance_eval"]["status"], "skipped")


class LatencyMetricTests(unittest.TestCase):
    def test_percentile_and_p95(self) -> None:
        from eval.metrics import latency_p95, percentile

        values = [1.0, 2.0, 3.0, 4.0, 100.0]
        self.assertEqual(percentile([], 95), None)
        self.assertAlmostEqual(percentile([7.0], 95) or 0, 7.0)
        self.assertAlmostEqual(latency_p95(values) or 0, 100.0)
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 50) or 0, 2.0)


class MLflowTrackingTests(unittest.TestCase):
    def test_resolve_params_and_extract_metrics(self) -> None:
        from eval.mlflow_tracking import extract_eval_metrics, resolve_eval_params

        params = resolve_eval_params(
            {"compliance": {"model": "gpt-4o-mini", "top_k": 5, "prompt_version": "v1"}},
            top_k=3,
            prompt_version="v2",
        )
        self.assertEqual(params["top_k"], "3")
        self.assertEqual(params["prompt_version"], "v2")
        self.assertEqual(params["model"], "gpt-4o-mini")
        self.assertIn("subprocessor", params["check_types"])

        report = {
            "compliance_eval": {
                "compliance": {
                    "overall": {"precision": 0.5, "recall": 1.0, "f1": 2 / 3}
                },
                "verifier": {"quote_valid_rate": 0.9},
            },
            "latency": {"p95_sec": 12.5},
        }
        metrics = extract_eval_metrics(report)
        self.assertAlmostEqual(metrics["precision"], 0.5)
        self.assertAlmostEqual(metrics["recall"], 1.0)
        self.assertAlmostEqual(metrics["quote_valid_rate"], 0.9)
        self.assertAlmostEqual(metrics["latency_p95"], 12.5)

    def test_oracle_logs_mlflow_run(self) -> None:
        try:
            import mlflow  # noqa: F401
        except ImportError:
            self.skipTest("mlflow not installed")

        from eval.compare_runs import fetch_runs
        from eval.run_eval import main

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_path = Path(tmp)
            out = tmp_path / "eval.json"
            tracking = tmp_path / "mlruns"
            experiment = "day9-unit-test"
            code = main(
                [
                    "--oracle",
                    "--skip-segmentation",
                    "--mlflow",
                    "--experiment",
                    experiment,
                    "--run-name",
                    "oracle_topk3",
                    "--top-k",
                    "3",
                    "--prompt-version",
                    "v1",
                    "--tracking-uri",
                    str(tracking),
                    "--out",
                    str(out),
                    "--report-dir",
                    str(tmp_path / "reports"),
                ]
            )
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("mlflow_run_id", payload)
            self.assertEqual(payload["params"]["top_k"], "3")
            self.assertEqual(payload["params"]["prompt_version"], "v1")
            self.assertIn("latency", payload)

            # Second run with different top_k for compare_runs.
            code2 = main(
                [
                    "--oracle",
                    "--skip-segmentation",
                    "--mlflow",
                    "--experiment",
                    experiment,
                    "--run-name",
                    "oracle_topk8",
                    "--top-k",
                    "8",
                    "--prompt-version",
                    "v2",
                    "--tracking-uri",
                    str(tracking),
                    "--out",
                    str(tmp_path / "eval2.json"),
                    "--report-dir",
                    str(tmp_path / "reports2"),
                ]
            )
            self.assertEqual(code2, 0)

            rows = fetch_runs(
                experiment_name=experiment,
                tracking_uri=str(tracking),
                max_runs=10,
            )
            self.assertGreaterEqual(len(rows), 2)
            top_ks = {str(r.get("top_k")) for r in rows}
            self.assertIn("3", top_ks)
            self.assertIn("8", top_ks)
            for row in rows:
                self.assertAlmostEqual(row.get("f1") or 0, 1.0)

    def test_compare_runs_cli(self) -> None:
        try:
            import mlflow  # noqa: F401
        except ImportError:
            self.skipTest("mlflow not installed")

        from eval.compare_runs import main as compare_main
        from eval.run_eval import main as eval_main

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_path = Path(tmp)
            tracking = tmp_path / "mlruns"
            experiment = "day9-compare-cli"
            for top_k, name in ((3, "a"), (5, "b"), (8, "c")):
                code = eval_main(
                    [
                        "--oracle",
                        "--skip-segmentation",
                        "--mlflow",
                        "--experiment",
                        experiment,
                        "--run-name",
                        name,
                        "--top-k",
                        str(top_k),
                        "--tracking-uri",
                        str(tracking),
                        "--out",
                        str(tmp_path / f"{name}.json"),
                        "--report-dir",
                        str(tmp_path / f"reports_{name}"),
                    ]
                )
                self.assertEqual(code, 0)

            code = compare_main(
                [
                    "--experiment",
                    experiment,
                    "--tracking-uri",
                    str(tracking),
                    "--param",
                    "top_k",
                    "--json",
                ]
            )
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
