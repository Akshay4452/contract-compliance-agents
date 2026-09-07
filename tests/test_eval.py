"""Unit tests for Day 8 eval harness (no LLM, no Chroma)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eval.golden import (
    COMPLIANCE_CASES,
    load_compliance_cases,
    load_segmentation_cases,
    list_contract_ids,
)
from eval.metrics import (
    ComplianceMetrics,
    Confusion,
    span_overlap_ratio,
)
from eval.predictions import findings_from_golden, run_offline_contract, segment_contract
from eval.run_eval import run_eval
from src.segmenter.splitter import segment_text

ROOT = Path(__file__).resolve().parents[1]


class GoldenSetTests(unittest.TestCase):
    def test_compliance_cases_count(self) -> None:
        cases = load_compliance_cases()
        self.assertGreaterEqual(len(cases), 40)
        self.assertLessEqual(len(cases), 55)

    def test_compliance_cases_schema(self) -> None:
        cases = load_compliance_cases()
        check_types = {c.check_type for c in cases}
        self.assertEqual(
            check_types,
            {
                "subprocessor",
                "data_retention",
                "breach_notification",
                "liability_cap",
                "termination_data_return",
            },
        )
        for case in cases:
            self.assertTrue(case.contract_id)
            self.assertRegex(case.clause_id, r"^c\d+$")
            if case.expected_flag:
                self.assertTrue(case.evidence_must_contain)
                self.assertIn(case.expected_severity, {"high", "medium", "low"})

    def test_positive_evidence_in_clause(self) -> None:
        cases = load_compliance_cases()
        for contract_id in list_contract_ids():
            clauses = {c["id"]: c["text"] for c in segment_contract(contract_id)}
            for case in cases:
                if case.contract_id != contract_id or not case.expected_flag:
                    continue
                self.assertIn(case.clause_id, clauses)
                self.assertIn(case.evidence_must_contain, clauses[case.clause_id])

    def test_segmentation_cases_match_segmenter(self) -> None:
        for case in load_segmentation_cases():
            clauses = segment_contract(case.contract_id)
            self.assertEqual(len(clauses), case.expected_clause_count)

    def test_jsonl_is_valid(self) -> None:
        raw = COMPLIANCE_CASES.read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len([l for l in raw if l.strip()]), 40)
        for line in raw:
            if line.strip():
                json.loads(line)


class MetricsTests(unittest.TestCase):
    def test_confusion_prf(self) -> None:
        c = Confusion()
        c.add(True, True)
        c.add(True, False)
        c.add(False, True)
        c.add(False, False)
        self.assertEqual(c.tp, 1)
        self.assertEqual(c.fp, 1)
        self.assertEqual(c.fn, 1)
        self.assertEqual(c.tn, 1)
        self.assertAlmostEqual(c.precision, 0.5)
        self.assertAlmostEqual(c.recall, 0.5)
        self.assertAlmostEqual(c.f1, 0.5)

    def test_compliance_metrics_by_check(self) -> None:
        m = ComplianceMetrics()
        m.observe(
            check_type="subprocessor",
            predicted_flag=True,
            expected_flag=True,
            predicted_severity="high",
            expected_severity="high",
        )
        m.observe(
            check_type="subprocessor",
            predicted_flag=False,
            expected_flag=False,
        )
        self.assertEqual(m.overall.tp, 1)
        self.assertEqual(m.overall.tn, 1)
        self.assertEqual(m.severity_accuracy, 1.0)

    def test_span_overlap(self) -> None:
        pred = [(0, 100), (100, 200)]
        gold = [(10, 90)]
        score = span_overlap_ratio(pred, gold)
        self.assertGreater(score, 0.5)
        self.assertEqual(span_overlap_ratio([], []), 1.0)
        self.assertEqual(span_overlap_ratio([(0, 10)], []), 0.0)


class OfflinePredictionsTests(unittest.TestCase):
    def test_findings_from_golden(self) -> None:
        cases = load_compliance_cases()
        clauses = segment_contract("synthetic_01")
        findings = findings_from_golden("synthetic_01", clauses, cases)
        self.assertGreaterEqual(len(findings), 5)
        for f in findings:
            self.assertTrue(f["evidence_quote"])
            clause = next(c for c in clauses if c["id"] == f["clause_id"])
            self.assertIn(f["evidence_quote"], clause["text"])

    def test_hallucinated_quotes(self) -> None:
        cases = load_compliance_cases()
        clauses = segment_contract("synthetic_01")
        findings = findings_from_golden(
            "synthetic_01", clauses, cases, hallucinate_every_n=1
        )
        self.assertTrue(
            all(
                f["evidence_quote"] == "THIS QUOTE DOES NOT APPEAR IN THE CLAUSE"
                for f in findings
            )
        )

    def test_offline_contract_runs_verifier(self) -> None:
        cases = load_compliance_cases()
        result = run_offline_contract("synthetic_04", cases)
        self.assertEqual(result["mode"], "offline")
        # clean contract → no positives in golden for flags on topic clauses
        # but synthetic_04 has only expected_flag=false rows → 0 findings
        self.assertEqual(len(result["findings"]), 0)


class RunEvalSmokeTests(unittest.TestCase):
    def test_offline_baseline_perfect_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "baseline.json"
            report = run_eval(
                mode="offline",
                hallucinate_every_n=0,
                include_cuad=False,
                out_path=out,
            )
            self.assertTrue(out.is_file())
            self.assertEqual(report["metrics"]["compliance"]["overall"]["f1"], 1.0)
            self.assertEqual(report["metrics"]["segmentation"]["accuracy"], 1.0)
            self.assertEqual(report["metrics"]["verifier"]["quote_valid_rate"], 1.0)

    def test_offline_with_hallucinations_lowers_quote_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "baseline.json"
            report = run_eval(
                mode="offline",
                hallucinate_every_n=2,
                include_cuad=False,
                out_path=out,
            )
            rate = report["metrics"]["verifier"]["quote_valid_rate"]
            self.assertLess(rate, 1.0)
            self.assertGreater(rate, 0.0)


if __name__ == "__main__":
    unittest.main()
