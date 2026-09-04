"""Day 5 compliance check types (fixed set of five — do not expand)."""

from __future__ import annotations

from enum import Enum


class CheckType(str, Enum):
    SUBPROCESSOR = "subprocessor"
    DATA_RETENTION = "data_retention"
    BREACH_NOTIFICATION = "breach_notification"
    LIABILITY_CAP = "liability_cap"
    TERMINATION_DATA_RETURN = "termination_data_return"


CHECK_TYPES: tuple[CheckType, ...] = tuple(CheckType)

# Short RAG queries — must fit the embedding model window (256 WordPieces).
RAG_QUERIES: dict[CheckType, str] = {
    CheckType.SUBPROCESSOR: (
        "subprocessor third-party personal data sharing authorization notification"
    ),
    CheckType.DATA_RETENTION: (
        "personal data retention storage limitation deletion erasure"
    ),
    CheckType.BREACH_NOTIFICATION: (
        "personal data breach notification timing controller processor"
    ),
    CheckType.LIABILITY_CAP: (
        "liability limitation damages cap contractual remedies"
    ),
    CheckType.TERMINATION_DATA_RETURN: (
        "termination end of processing return delete personal data"
    ),
}

CHECK_DESCRIPTIONS: dict[CheckType, str] = {
    CheckType.SUBPROCESSOR: (
        "Subprocessor / third-party sharing: whether the vendor may share personal "
        "data with subprocessors or other third parties, and whether customer "
        "approval or notice is required."
    ),
    CheckType.DATA_RETENTION: (
        "Data retention / deletion: how long personal data may be kept and whether "
        "deletion or return is required when no longer needed."
    ),
    CheckType.BREACH_NOTIFICATION: (
        "Breach notification timing: whether and how quickly the vendor must notify "
        "the customer of a personal data breach."
    ),
    CheckType.LIABILITY_CAP: (
        "Liability cap present/absent: whether there is a clear maximum payout "
        "(limitation of liability) if things go wrong."
    ),
    CheckType.TERMINATION_DATA_RETURN: (
        "Termination / data return on exit: when the agreement ends, whether the "
        "vendor must return or delete customer personal data."
    ),
}
