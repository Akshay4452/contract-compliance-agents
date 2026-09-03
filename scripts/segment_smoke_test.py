"""Smoke-test the Day 3 rule-based segmenter (no LLM, no Chroma)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.segmenter.models import SegmentedDocument
from src.segmenter.splitter import segment_text
from src.segmenter.store import dump_documents, load_documents, segment_file

MSA = ROOT / "data" / "templates" / "saas_msa.txt"
NDA = ROOT / "data" / "templates" / "nda_mutual.txt"
DPA = ROOT / "data" / "templates" / "dpa_processor.txt"
SAMPLES = [
    ROOT / "data" / "samples" / "consulting_agreement.txt",
    ROOT / "data" / "samples" / "vendor_security_addendum.txt",
]

NUMBERED_FIXTURE = """CO-BRANDING AGREEMENT

This is the preamble between two companies about a joint site.

1. DEFINITIONS.

Content means text and images. Domain Name means example.com.

2. DEVELOPMENT AND IMPLEMENTATION.

2.1 OVERVIEW. Each party hosts its own pages.
2.2 LAUNCH TIMING. Launch within four months.

3. PROMOTION.

After launch, the retailer will promote the services.

10. LIMITATION ON LIABILITY.

Neither party is liable for consequential damages.

11. INDEMNITY.

Each party shall indemnify the other against third-party claims.
"""


def _assert_ids_and_offsets(text: str, clauses) -> None:
    assert clauses, "expected at least one clause"
    ids = [clause.id for clause in clauses]
    assert ids == [f"c{i}" for i in range(1, len(clauses) + 1)], ids
    for clause in clauses:
        assert clause.text, clause.id
        assert clause.start_hint >= 0, clause.id
        snippet = text[clause.start_hint : clause.start_hint + min(40, len(clause.text))]
        assert clause.text.startswith(snippet) or snippet in clause.text, (
            f"{clause.id} start_hint={clause.start_hint} does not land on clause text"
        )


def test_numbered_fixture() -> None:
    clauses = segment_text(NUMBERED_FIXTURE)
    titles = [clause.title for clause in clauses]
    print("fixture titles:", titles)
    assert any("Preamble" == c.title or "CO-BRANDING" in c.title for c in clauses)
    assert any("DEFINITIONS" in c.title for c in clauses)
    assert any("DEVELOPMENT" in c.title for c in clauses)
    assert any("PROMOTION" in c.title for c in clauses)
    assert any("LIMITATION" in c.title for c in clauses)
    assert any("INDEMNITY" in c.title for c in clauses)

    development = next(c for c in clauses if "DEVELOPMENT" in c.title)
    assert "2.1 OVERVIEW" in development.text
    assert "2.2 LAUNCH TIMING" in development.text

    _assert_ids_and_offsets(NUMBERED_FIXTURE, clauses)


def test_msa_has_liability_and_indemnity() -> None:
    text = MSA.read_text(encoding="utf-8")
    clauses = segment_text(text)
    _assert_ids_and_offsets(text, clauses)
    blob = " ".join(c.title for c in clauses)
    assert "INDEMNIFICATION" in blob
    assert "LIMITATION OF LIABILITY" in blob
    liability = next(c for c in clauses if "LIMITATION OF LIABILITY" in c.title)
    assert "twelve (12) months" in liability.text
    assert "10.1" in liability.text
    assert "10.2" in liability.text
    print(f"MSA clauses={len(clauses)}  liability chars={len(liability.text)}")


def test_templates_split() -> None:
    for path in (NDA, MSA, DPA):
        doc = segment_file(path, source_kind="template")
        assert len(doc.clauses) >= 5, f"{path.name} only {len(doc.clauses)} clauses"
        print(f"{doc.document_id}: {len(doc.clauses)} clauses")


def test_five_files_have_required_shape() -> None:
    paths = [NDA, MSA, DPA, *SAMPLES]
    for path in paths:
        doc = segment_file(path)
        assert doc.document_id
        assert len(doc.clauses) >= 5, path.name
        for clause in doc.clauses:
            assert clause.id.startswith("c")
            assert clause.text
            assert isinstance(clause.start_hint, int) and clause.start_hint >= 0
    print(f"shape check: {len(paths)} documents, required fields present")


def test_json_roundtrip() -> None:
    docs = [
        segment_file(NDA, source_kind="template"),
        segment_file(MSA, source_kind="template"),
        segment_file(DPA, source_kind="template"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clauses.json"
        dump_documents(docs, out)
        loaded = load_documents(out)
    assert [d.document_id for d in loaded] == [d.document_id for d in docs]
    assert all(isinstance(d, SegmentedDocument) for d in loaded)
    assert loaded[1].clauses[0].id == "c1"
    print(f"roundtrip documents={len(loaded)}")


def main() -> None:
    test_numbered_fixture()
    test_msa_has_liability_and_indemnity()
    test_templates_split()
    test_five_files_have_required_shape()
    test_json_roundtrip()
    print("\nSMOKE PASS")


if __name__ == "__main__":
    main()
