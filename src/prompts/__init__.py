"""Load prompt text files from ``src/prompts/``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    """Read ``src/prompts/<name>`` (e.g. ``compliance_system.txt``)."""
    path = PROMPTS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip() + "\n"


def load_compliance_system_prompt() -> str:
    return load_prompt("compliance_system.txt")


def load_compliance_user_template() -> str:
    return load_prompt("compliance_user.txt")
