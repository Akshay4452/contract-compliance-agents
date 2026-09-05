"""Unit tests for Day 7 reporter (no LLM)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.reporter.agent import run_reporter
from src.reporter.markdown import render_audit_markdown


def _sample_clauses() -> list[dict]:
    return [
        {
            "id": "c1",
            "title": "SUBPROCESSORS",
            "text": "Vendor may share data without prior notice to Customer.",
        },
        {
            "id": "c2",
            "title": "DATA RETENTION",
            "text": "Vendor keeps data as long as Vendor deems useful.",
        },
    ]


def _sample_findings() -> tuple[list[dict], list[dict]]:
    verified = [
        {
            "finding_id": "c1:subprocessor",
            "clause_id": "c1",
            "check_type": "subprocessor",
            "issue": "Open sharing",
            "evidence_quote": "without prior notice",
            "regulation_ref": "GDPR 28",
            "severity": "high",
            "confidence": 0.9,
            "verified": True,
            "reject_reason": "",
        }
    ]
    rejected = [
        {
            "finding_id": "c1:hallucinated",
            "clause_id": "c1",
            "check_type": "subprocessor",
            "issue": "Invented quote",
            "evidence_quote": "always requires written approval",
            "regulation_ref": "GDPR 28",
            "severity": "high",
            "confidence": 0.95,
            "verified": False,
            "reject_reason": "quote_not_in_clause",
        }
    ]
    return verified + rejected, verified


class MarkdownTests(unittest.TestCase):
    def test_sections_and_appendix(self) -> None:
        all_findings, verified = _sample_findings()
        rejected = [f for f in all_findings if not f.get("verified")]
        md = render_audit_markdown(
            document_id="demo",
            source_path="/tmp/demo.txt",
            clause_count=2,
            verified_findings=verified,
            rejected_findings=rejected,
            clauses=_sample_clauses(),
            status="pending_review",
        )
        self.assertIn("pending_review", md)
        self.assertIn("## Executive summary", md)
        self.assertIn("## Verified findings", md)
        self.assertIn("## Appendix — verifier rejected", md)
        self.assertIn("without prior notice", md)
        self.assertIn("quote_not_in_clause", md)


class ReporterAgentTests(unittest.TestCase):
    def test_pending_review_and_artifacts(self) -> None:
        all_findings, verified = _sample_findings()
        with tempfile.TemporaryDirectory() as tmp:
            payload, findings_doc = run_reporter(
                document_id="unit_demo",
                source_path="/tmp/demo.txt",
                clauses=_sample_clauses(),
                findings=all_findings,
                verified_findings=verified,
                auto_approve=False,
                write=True,
                out_dir=Path(tmp),
            )
            self.assertEqual(payload["status"], "pending_review")
            self.assertEqual(payload["finding_count"], 1)
            self.assertEqual(findings_doc["verified_count"], 1)
            self.assertEqual(findings_doc["rejected_count"], 1)
            findings_path = Path(payload["findings_json_path"])
            audit_path = Path(payload["audit_report_path"])
            self.assertTrue(findings_path.is_file())
            self.assertTrue(audit_path.is_file())
            self.assertIn("Audit report", audit_path.read_text(encoding="utf-8"))

    def test_auto_approve(self) -> None:
        all_findings, verified = _sample_findings()
        payload, _ = run_reporter(
            document_id="unit_demo",
            source_path="/tmp/demo.txt",
            clauses=_sample_clauses(),
            findings=all_findings,
            verified_findings=verified,
            auto_approve=True,
            write=False,
        )
        self.assertEqual(payload["status"], "approved")
        self.assertNotIn("findings_json_path", payload)


if __name__ == "__main__":
    unittest.main()
