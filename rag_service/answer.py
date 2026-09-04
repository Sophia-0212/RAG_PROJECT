from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Citation:
    citation_id: str
    source_uri: str
    source_id: str
    document_id: str
    version_id: str
    chunk_id: str
    title: str = ""


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    citations: tuple[Citation, ...] = ()
    refusal_reason: str | None = None
    degraded: bool = False

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": [asdict(citation) for citation in self.citations],
            "refusal_reason": self.refusal_reason,
            "degraded": self.degraded,
        }
