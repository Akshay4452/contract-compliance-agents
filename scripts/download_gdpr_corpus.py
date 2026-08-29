"""Download GDPR regulatory corpus for RAG (Day 1)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "data_paths.yaml"


def main() -> None:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["gdpr"]

    hf_id = cfg["hf_dataset"]
    out_dir = ROOT / "data" / "regulations" / "gdpr-en"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {hf_id} ...")
    ds = load_dataset(hf_id, split="train")
    records = [dict(row) for row in ds]
    for row in records:
        for key, value in list(row.items()):
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat()

    out_file = out_dir / "train.json"
    out_file.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Saved {len(records)} records -> {out_file}")
    if records:
        print("Sample keys:", list(records[0].keys()))
        print("First record preview:")
        preview = {k: (str(v)[:120] + "..." if len(str(v)) > 120 else v) for k, v in records[0].items()}
        for k, v in preview.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
