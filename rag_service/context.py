from __future__ import annotations

from dataclasses import dataclass
import math
import unicodedata
from typing import Mapping, Protocol, Sequence

import tiktoken
from langchain_core.documents import Document

from rag_service.answer import Citation
from rag_service.retrieval import RetrievalCandidate, authorize_candidates, deduplicate_candidates
from rag_service.security import RequestContext, is_document_authorized


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...

    def truncate(self, text: str, max_tokens: int) -> str: ...


class TiktokenTokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text))

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        tokens = self.encoding.encode(text)
        return self.encoding.decode(tokens[:max_tokens])


class ConservativeTokenCounter:
    """Offline-safe estimator that intentionally overestimates token usage."""

    @staticmethod
    def _weight(character: str) -> float:
        if character.isspace():
            return 0.25
        if ord(character) < 128 and (character.isalnum() or character in {"_", "-"}):
            return 0.25
        if unicodedata.category(character).startswith("M"):
            return 0.0
        return 1.0

    def count(self, text: str) -> int:
        return math.ceil(sum(self._weight(character) for character in text))

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        result = []
        weight = 0.0
        for character in text:
            next_weight = weight + self._weight(character)
            if math.ceil(next_weight) > max_tokens:
                break
            result.append(character)
            weight = next_weight
        return "".join(result)


@dataclass(frozen=True)
class ContextBlock:
    citation: Citation
    text: str
    token_count: int
    fused_score: float | None
    rerank_score: float | None

    def render(self) -> str:
        label = self.citation.title or self.citation.source_uri
        return f"[{self.citation.citation_id}] {label} (version={self.citation.version_id})\n{self.text}"


@dataclass(frozen=True)
class ContextPack:
    blocks: tuple[ContextBlock, ...]
    token_count: int
    truncated: bool

    @property
    def citations(self) -> tuple[Citation, ...]:
        return tuple(block.citation for block in self.blocks)

    def render(self) -> str:
        return "\n\n".join(block.render() for block in self.blocks)


def _expanded_document(
    candidate: RetrievalCandidate,
    parent_documents: Mapping[str, Document],
    context: RequestContext,
) -> Document:
    parent_chunk_id = candidate.document.metadata.get("parent_chunk_id")
    if not parent_chunk_id:
        return candidate.document
    parent = parent_documents.get(str(parent_chunk_id))
    if parent is None or not is_document_authorized(parent, context):
        return candidate.document
    if parent.metadata.get("version_id") != candidate.document.metadata.get("version_id"):
        return candidate.document
    return parent


def pack_context(
    candidates: Sequence[RetrievalCandidate],
    *,
    context: RequestContext,
    max_tokens: int,
    token_counter: TokenCounter | None = None,
    parent_documents: Mapping[str, Document] | None = None,
) -> ContextPack:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")
    counter = token_counter or ConservativeTokenCounter()
    parents = parent_documents or {}
    blocks: list[ContextBlock] = []
    used_tokens = 0
    truncated = False

    ranked = sorted(
        deduplicate_candidates(authorize_candidates(candidates, context)),
        key=lambda item: (
            item.rerank_score is not None,
            item.rerank_score if item.rerank_score is not None else item.fused_score or 0.0,
            -item.recall_rank,
        ),
        reverse=True,
    )
    for candidate in ranked:
        document = _expanded_document(candidate, parents, context)
        metadata = document.metadata
        required = ("source_uri", "source_id", "document_id", "version_id", "chunk_id")
        if any(not metadata.get(field) for field in required):
            continue
        citation_id = f"S{len(blocks) + 1}"
        citation = Citation(
            citation_id=citation_id,
            source_uri=str(metadata["source_uri"]),
            source_id=str(metadata["source_id"]),
            document_id=str(metadata["document_id"]),
            version_id=str(metadata["version_id"]),
            chunk_id=str(metadata["chunk_id"]),
            title=str(metadata.get("title", "")),
        )
        header = f"[{citation_id}] {citation.title or citation.source_uri} (version={citation.version_id})\n"
        header_tokens = counter.count(header)
        remaining = max_tokens - used_tokens - header_tokens
        if remaining <= 0:
            truncated = True
            break
        text = document.page_content
        text_tokens = counter.count(text)
        if text_tokens > remaining:
            truncated = True
            if blocks:
                continue
            text = counter.truncate(text, remaining)
            text_tokens = counter.count(text)
        block_tokens = header_tokens + text_tokens
        blocks.append(
            ContextBlock(
                citation=citation,
                text=text,
                token_count=block_tokens,
                fused_score=candidate.fused_score,
                rerank_score=candidate.rerank_score,
            )
        )
        used_tokens += block_tokens
    return ContextPack(blocks=tuple(blocks), token_count=used_tokens, truncated=truncated)
