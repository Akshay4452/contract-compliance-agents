"""Load Day 8 golden fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "data" / "golden"
CONTRACTS_DIR = GOLDEN_DIR / "contracts"
COMPLIANCE_CASES = GOLDEN_DIR / "compliance_cases.jsonl"
SEGMENTATION_CASES = GOLDEN_DIR / "segmentation_cases.jsonl"


@dataclass(frozen=True)
class ComplianceCase:
    contract_id: str
    clause_id: str
    check_type: str
    expected_flag: bool
    expected_severity: str | None = None
    notes: str = ""
    evidence_must_contain: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.contract_id, self.clause_id, self.check_type)


@dataclass(frozen=True)
class SegmentationCase:
    contract_id: str
    expected_clause_count: int
    tolerance: int = 0
    source: str = "synthetic"
    notes: str = ""


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected object")
            yield row


def load_compliance_cases(path: Path | None = None) -> list[ComplianceCase]:
    path = path or COMPLIANCE_CASES
    cases: list[ComplianceCase] = []
    for row in _iter_jsonl(path):
        cases.append(
            ComplianceCase(
                contract_id=str(row["contract_id"]),
                clause_id=str(row["clause_id"]),
                check_type=str(row["check_type"]),
                expected_flag=bool(row["expected_flag"]),
                expected_severity=(
                    None
                    if row.get("expected_severity") in (None, "")
                    else str(row["expected_severity"])
                ),
                notes=str(row.get("notes") or ""),
                evidence_must_contain=str(row.get("evidence_must_contain") or ""),
            )
        )
    return cases


def load_segmentation_cases(path: Path | None = None) -> list[SegmentationCase]:
    path = path or SEGMENTATION_CASES
    cases: list[SegmentationCase] = []
    for row in _iter_jsonl(path):
        cases.append(
            SegmentationCase(
                contract_id=str(row["contract_id"]),
                expected_clause_count=int(row["expected_clause_count"]),
                tolerance=int(row.get("tolerance") or 0),
                source=str(row.get("source") or "synthetic"),
                notes=str(row.get("notes") or ""),
            )
        )
    return cases


def contract_path(contract_id: str, contracts_dir: Path | None = None) -> Path:
    directory = contracts_dir or CONTRACTS_DIR
    path = directory / f"{contract_id}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"missing golden contract: {path}")
    return path


def list_contract_ids(contracts_dir: Path | None = None) -> list[str]:
    directory = contracts_dir or CONTRACTS_DIR
    return sorted(p.stem for p in directory.glob("*.txt"))
