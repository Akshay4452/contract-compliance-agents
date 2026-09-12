"""Load Day 8 golden cases and resolve contract paths."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "data" / "golden" / "compliance_cases.jsonl"
DEFAULT_INDEX = ROOT / "data" / "golden" / "contracts_index.yaml"


@dataclass(frozen=True)
class GoldenCase:
    """One labeled (contract, clause, check) expectation."""

    contract_id: str
    clause_id: str
    check_type: str
    expected_flag: bool
    expected_severity: str | None
    notes: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.contract_id, self.clause_id, self.check_type)


def load_contracts_index(
    path: Path | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    """Map ``contract_id`` → absolute ``.txt`` path."""
    root = root or ROOT
    index_path = path or DEFAULT_INDEX
    raw = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    out: dict[str, Path] = {}
    for contract_id, rel in raw.items():
        p = Path(str(rel))
        if not p.is_absolute():
            p = root / p
        out[str(contract_id)] = p
    return out


def load_golden_cases(path: Path | None = None) -> list[GoldenCase]:
    """Parse ``compliance_cases.jsonl``."""
    golden_path = path or DEFAULT_GOLDEN
    cases: list[GoldenCase] = []
    for line_no, line in enumerate(
        golden_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            row: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{golden_path}:{line_no}: invalid JSON") from exc

        severity = row.get("expected_severity")
        if severity is not None:
            severity = str(severity)

        cases.append(
            GoldenCase(
                contract_id=str(row["contract_id"]),
                clause_id=str(row["clause_id"]),
                check_type=str(row["check_type"]),
                expected_flag=bool(row["expected_flag"]),
                expected_severity=severity,
                notes=str(row.get("notes") or ""),
            )
        )

    if not cases:
        raise ValueError(f"no golden cases in {golden_path}")
    return cases


def validate_golden_against_segmenter(
    cases: list[GoldenCase],
    contracts: dict[str, Path],
) -> list[str]:
    """Return human-readable problems (empty = OK)."""
    from src.segmenter.splitter import segment_text

    errors: list[str] = []
    by_contract: dict[str, list[GoldenCase]] = {}
    for case in cases:
        by_contract.setdefault(case.contract_id, []).append(case)

    for contract_id, rows in sorted(by_contract.items()):
        path = contracts.get(contract_id)
        if path is None:
            errors.append(f"{contract_id}: missing from contracts_index")
            continue
        if not path.is_file():
            errors.append(f"{contract_id}: contract file not found: {path}")
            continue
        clauses = segment_text(path.read_text(encoding="utf-8", errors="replace"))
        ids = {c.id for c in clauses}
        for case in rows:
            if case.clause_id not in ids:
                errors.append(
                    f"{contract_id}/{case.clause_id}/{case.check_type}: "
                    f"clause_id not in segmenter output {sorted(ids)}"
                )
    return errors
