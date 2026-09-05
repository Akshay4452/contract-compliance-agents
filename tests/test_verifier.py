"""Unit tests for Day 6 verifier (no LLM, no Chroma)."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.verifier.agent import run_verifier, verify_finding
from src.verifier.corpus import CorpusCatalog, build_catalog_from_records
from src.verifier.rules import (
    extract_article_numbers,
    quote_in_clause,
    regulation_ref_known,
)

ROOT = Path(__file__).resolve().parents[1]


def _toy_catalog() -> CorpusCatalog:
    records = [
        {
            "id": 28,
            "type": "article",
            "article_number": "28",
            "title": "Processor",
            "source_url": "https://eur-lex.europa.eu/example",
        },
        {
            "id": 32,
            "type": "article",
            "article_number": "32",
            "title": "Security of processing",
            "source_url": "https://eur-lex.europa.eu/example",
        },
        {
            "id": 99,
            "type": "qa",
            "category": "Breach notification timing",
            "source_url": "gdpr-en",
        },
    ]
    return build_catalog_from_records(records)


class QuoteRulesTests(unittest.TestCase):
    def test_exact_substring(self) -> None:
        clause = "Vendor may share data without prior notice to Customer."
        self.assertTrue(quote_in_clause("without prior notice", clause))

    def test_fuzzy_whitespace(self) -> None:
        clause = "Vendor may share   data\nwithout prior notice."
        self.assertTrue(
            quote_in_clause("without  prior   notice", clause, fuzzy=True)
        )
        self.assertFalse(
            quote_in_clause("without  prior   notice", clause, fuzzy=False)
        )

    def test_hallucinated_quote(self) -> None:
        clause = "Fees are due within thirty days."
        self.assertFalse(quote_in_clause("without prior notice", clause))


class RegulationRefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = _toy_catalog()

    def test_extract_article_numbers(self) -> None:
        self.assertEqual(extract_article_numbers("GDPR 28 (Processor)"), ["28"])
        self.assertEqual(extract_article_numbers("Article 32"), ["32"])
        self.assertEqual(extract_article_numbers("Art. 28"), ["28"])

    def test_known_gdpr_article_ref(self) -> None:
        self.assertTrue(
            regulation_ref_known("GDPR 28 (Processor)", self.catalog)
        )

    def test_known_topic(self) -> None:
        self.assertTrue(
            regulation_ref_known("Breach notification timing", self.catalog)
        )

    def test_unknown_ref(self) -> None:
        self.assertFalse(
            regulation_ref_known("Made-up Regulation 999", self.catalog)
        )


class VerifyFindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = _toy_catalog()
        self.clause = (
            "1. SUBPROCESSORS\n\n"
            "Vendor may engage any third party without prior notice to Customer."
        )

    def _base(self, **overrides):
        row = {
            "finding_id": "c1:subprocessor",
            "clause_id": "c1",
            "check_type": "subprocessor",
            "issue": "Open third-party sharing",
            "evidence_quote": "without prior notice",
            "regulation_ref": "GDPR 28 (Processor)",
            "severity": "high",
            "confidence": 0.9,
        }
        row.update(overrides)
        return row

    def test_accepts_grounded_finding(self) -> None:
        out = verify_finding(
            self._base(),
            clause_text=self.clause,
            catalog=self.catalog,
            min_confidence=0.5,
        )
        self.assertTrue(out["verified"])
        self.assertEqual(out["reject_reason"], "")

    def test_rejects_hallucinated_quote(self) -> None:
        out = verify_finding(
            self._base(evidence_quote="Customer must approve every subprocessor"),
            clause_text=self.clause,
            catalog=self.catalog,
        )
        self.assertFalse(out["verified"])
        self.assertEqual(out["reject_reason"], "quote_not_in_clause")

    def test_rejects_unknown_regulation_ref(self) -> None:
        out = verify_finding(
            self._base(regulation_ref="Fake Law Section 12"),
            clause_text=self.clause,
            catalog=self.catalog,
        )
        self.assertFalse(out["verified"])
        self.assertEqual(out["reject_reason"], "regulation_ref_not_in_corpus")

    def test_rejects_low_confidence(self) -> None:
        out = verify_finding(
            self._base(confidence=0.2),
            clause_text=self.clause,
            catalog=self.catalog,
            min_confidence=0.5,
        )
        self.assertFalse(out["verified"])
        self.assertEqual(out["reject_reason"], "confidence_below_threshold")

    def test_rejects_missing_clause(self) -> None:
        out = verify_finding(
            self._base(),
            clause_text=None,
            catalog=self.catalog,
        )
        self.assertFalse(out["verified"])
        self.assertEqual(out["reject_reason"], "missing_clause")


class RunVerifierTests(unittest.TestCase):
    def test_filters_to_verified_only(self) -> None:
        catalog = _toy_catalog()
        clauses = [
            {
                "id": "c1",
                "text": "Vendor may share without prior notice.",
            }
        ]
        findings = [
            {
                "finding_id": "c1:subprocessor",
                "clause_id": "c1",
                "check_type": "subprocessor",
                "issue": "gap",
                "evidence_quote": "without prior notice",
                "regulation_ref": "GDPR 28",
                "severity": "high",
                "confidence": 0.9,
            },
            {
                "finding_id": "c1:hallucination",
                "clause_id": "c1",
                "check_type": "data_retention",
                "issue": "invented",
                "evidence_quote": "this quote is not in the clause at all",
                "regulation_ref": "GDPR 28",
                "severity": "high",
                "confidence": 0.95,
            },
        ]
        annotated, verified = run_verifier(
            findings,
            clauses,
            catalog=catalog,
            min_confidence=0.5,
        )
        self.assertEqual(len(annotated), 2)
        self.assertEqual(len(verified), 1)
        self.assertTrue(verified[0]["verified"])
        self.assertEqual(annotated[1]["reject_reason"], "quote_not_in_clause")

    def test_real_gdpr_json_catalog_loads(self) -> None:
        """Smoke that the on-disk corpus is readable for citation checks."""
        from src.verifier.corpus import load_corpus_catalog

        catalog = load_corpus_catalog(ROOT)
        self.assertTrue(catalog.articles)
        self.assertIn("28", catalog.articles)
        self.assertTrue(regulation_ref_known("GDPR 28 (Processor)", catalog))


if __name__ == "__main__":
    unittest.main()
