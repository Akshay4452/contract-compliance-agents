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


if __name__ == "__main__":
    unittest.main()
