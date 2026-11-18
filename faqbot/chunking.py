"""Load a folder of Markdown/text documents and split them into retrievable chunks.

Each chunk is one section (the text under a heading). Long sections are split
on paragraph boundaries so no chunk is much bigger than `max_chars`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED = {".md", ".markdown", ".txt"}
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class Chunk:
    id: str        # e.g. "menu.md#3"
    source: str    # file name
    title: str     # document title (first H1, else file name)
    heading: str   # section heading ("" for text before the first heading)
    text: str

    def label(self) -> str:
        return f"{self.title} > {self.heading}" if self.heading else self.title


def load_documents(folder: str | Path) -> dict[str, str]:
    """Return {file name: text} for every supported file in `folder` (sorted, non-recursive)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Documents folder not found: {folder}")
    docs = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith(".")
    }
    if not docs:
        raise FileNotFoundError(f"No .md or .txt files in {folder}")
    return docs


def split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split Markdown into (document title, [(heading, body), ...])."""
    title = ""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            level, heading = len(m.group(1)), m.group(2)
            if level == 1 and not title:
                title = heading
                continue
            sections.append((heading, []))
        else:
            sections[-1][1].append(line)
    cleaned = [(h, "\n".join(body).strip()) for h, body in sections]
    return title, [(h, b) for h, b in cleaned if b]


def pack_paragraphs(body: str, max_chars: int) -> list[str]:
    """Group paragraphs into pieces of at most ~max_chars (a single huge paragraph is kept whole)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    pieces, current = [], ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = para
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_document(name: str, text: str, max_chars: int = 900) -> list[Chunk]:
    title, sections = split_sections(text)
    title = title or Path(name).stem.replace("-", " ").replace("_", " ").title()
    chunks = []
    for heading, body in sections:
        for piece in pack_paragraphs(body, max_chars):
            chunks.append(Chunk(id=f"{name}#{len(chunks)}", source=name, title=title, heading=heading, text=piece))
    return chunks


def chunk_folder(folder: str | Path, max_chars: int = 900) -> list[Chunk]:
    chunks: list[Chunk] = []
    for name, text in load_documents(folder).items():
        chunks.extend(chunk_document(name, text, max_chars))
    return chunks
