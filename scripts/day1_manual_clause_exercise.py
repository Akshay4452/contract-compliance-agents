"""Day 1 exercise: manually split one contract into clauses (learning by doing)."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "data_paths.yaml"
OUT_DIR = ROOT / "data" / "exercises" / "day1_manual_split"


def split_naive(text: str) -> list[dict]:
    """Rule-based split on numbered sections (ARTICLE, Section, etc.)."""
    pattern = re.compile(
        r"(?m)^(?:ARTICLE\s+\d+|Section\s+\d+(?:\.\d+)*|SECTION\s+\d+)\b.*$"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return [{"clause_id": "c1", "title": "full_document", "text": text.strip()}]

    clauses: list[dict] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        title = match.group(0).strip().split("\n")[0][:120]
        clauses.append({"clause_id": f"c{i + 1}", "title": title, "text": chunk})
    return clauses


def main() -> None:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["cuad"]

    txt_dir = Path(cfg["contracts_txt_dir"])
    contract_path = sorted(txt_dir.glob("*.txt"))[0]
    text = contract_path.read_text(encoding="utf-8", errors="replace")

    clauses = split_naive(text)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_csv = OUT_DIR / "clauses_manual.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["clause_id", "title", "text"])
        writer.writeheader()
        writer.writerows(clauses)

    print(f"Contract: {contract_path.name}")
    print(f"Clauses found (naive): {len(clauses)}")
    print(f"Wrote: {out_csv}")
    print()
    print("Your task: open the CSV and read 3 clauses.")
    print("For each, write in plain English: what is this clause about?")


if __name__ == "__main__":
    main()
