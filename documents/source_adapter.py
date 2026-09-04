from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from documents.governance import SourceDocument, Visibility


@dataclass(frozen=True)
class MarkdownSourceAdapter:
    root: Path
    tenant_id: str
    acl_principals: tuple[str, ...]
    visibility: Visibility = Visibility.RESTRICTED

    def scan(self) -> list[tuple[Path, SourceDocument]]:
        root = self.root.resolve()
        sources: list[tuple[Path, SourceDocument]] = []
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            relative_uri = path.relative_to(root).as_posix()
            content = path.read_text(encoding="utf-8")
            title = self._first_heading(content) or path.stem
            source = SourceDocument(
                tenant_id=self.tenant_id,
                source_uri=relative_uri,
                content=content,
                title=title,
                acl_principals=self.acl_principals,
                visibility=self.visibility,
            )
            sources.append((path, source))
        return sources

    @staticmethod
    def _first_heading(content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return ""
