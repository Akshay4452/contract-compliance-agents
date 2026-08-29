"""Inspect local CUAD v1 installation and print dataset stats."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "data_paths.yaml"


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    cfg = load_config()["cuad"]
    txt_dir = Path(cfg["contracts_txt_dir"])
    master_csv = Path(cfg["master_clauses_csv"])
    squad_json = Path(cfg["squad_json"])

    for path in (txt_dir, master_csv, squad_json):
        if not path.exists():
            raise FileNotFoundError(f"Missing CUAD path: {path}")

    contract_files = sorted(txt_dir.glob("*.txt"))
    master = pd.read_csv(master_csv)
    with squad_json.open(encoding="utf-8") as f:
        squad = json.load(f)

    qa_count = len(squad.get("data", []))

    print("=== CUAD v1 inspection ===")
    print(f"Contracts (txt):     {len(contract_files)}")
    print(f"Master clauses rows: {len(master)} (includes header row)")
    print(f"SQuAD-style QAs:     {qa_count}")
    print(f"Label columns:       {master.shape[1] - 1} categories")
    print()
    print("Sample contract files:")
    for p in contract_files[:3]:
        size_kb = p.stat().st_size / 1024
        print(f"  - {p.name} ({size_kb:.1f} KB)")
    print()
    print("First contract preview (500 chars):")
    sample = contract_files[0].read_text(encoding="utf-8", errors="replace")
    print(sample[:500].replace("\n", " ") + "...")
    print()
    print("OK: CUAD paths valid. Use full 510 for eval; use 5-10 for daily dev runs.")


if __name__ == "__main__":
    main()
