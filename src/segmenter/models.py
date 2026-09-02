"""Clause and document shapes reused later as LangGraph state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Clause:
    """One unit of work for downstream agents.

    ``start_hint`` is the character offset of this clause in the original
    document text (after skipping leading whitespace in the slice).
    """

    id: str
    text: str
    start_hint: int
    title: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SegmentedDocument:
    """Graph-ready container: ``document_id`` + ``clauses[]``."""

    document_id: str
    clauses: list[Clause] = field(default_factory=list)
    source_path: str = ""
    source_kind: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "source_kind": self.source_kind,
            "clause_count": len(self.clauses),
            "clauses": [clause.to_dict() for clause in self.clauses],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> SegmentedDocument:
        clauses = [
            Clause(
                id=str(item["id"]),
                text=str(item["text"]),
                start_hint=int(item["start_hint"]),
                title=str(item.get("title") or ""),
            )
            for item in payload.get("clauses") or []
        ]
        return cls(
            document_id=str(payload["document_id"]),
            clauses=clauses,
            source_path=str(payload.get("source_path") or ""),
            source_kind=str(payload.get("source_kind") or "unknown"),
        )
