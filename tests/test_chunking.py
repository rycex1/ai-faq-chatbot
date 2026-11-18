import pytest

from faqbot.chunking import chunk_document, chunk_folder, load_documents, pack_paragraphs, split_sections
from faqbot.config import PROJECT_ROOT

DOC = """# Store Policies

Intro line before any section.

## Payment

We accept cash and cards.

## Refunds

Full refund up to 72 hours before pickup.

### Cakes

Custom cakes cannot be refunded once decorating starts.
"""


def test_split_sections_uses_h1_as_title():
    title, sections = split_sections(DOC)
    assert title == "Store Policies"
    assert [h for h, _ in sections] == ["", "Payment", "Refunds", "Cakes"]
    assert sections[0][1] == "Intro line before any section."


def test_chunk_document_ids_and_labels():
    chunks = chunk_document("policies.md", DOC)
    assert [c.id for c in chunks] == ["policies.md#0", "policies.md#1", "policies.md#2", "policies.md#3"]
    assert chunks[1].label() == "Store Policies > Payment"
    assert chunks[0].label() == "Store Policies"
    assert all(c.source == "policies.md" for c in chunks)


def test_title_falls_back_to_file_name():
    chunks = chunk_document("opening-hours.txt", "We open at 7.\n\nWe close at 6.")
    assert chunks[0].title == "Opening Hours"
    assert chunks[0].text == "We open at 7.\n\nWe close at 6."


def test_pack_paragraphs_respects_max_chars():
    body = "\n\n".join(f"Paragraph {i} " + "x" * 80 for i in range(10))
    pieces = pack_paragraphs(body, max_chars=200)
    assert len(pieces) == 5
    assert all(len(p) <= 200 for p in pieces)
    assert "".join(pieces).count("Paragraph") == 10  # nothing lost


def test_long_paragraph_is_kept_whole():
    long = "y" * 2000
    assert pack_paragraphs(long, max_chars=100) == [long]


def test_load_documents_filters_types(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\ntext", encoding="utf-8")
    (tmp_path / "b.txt").write_text("plain", encoding="utf-8")
    (tmp_path / "c.pdf").write_bytes(b"%PDF")
    (tmp_path / ".hidden.md").write_text("x", encoding="utf-8")
    assert list(load_documents(tmp_path)) == ["a.md", "b.txt"]


def test_load_documents_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_documents(tmp_path / "missing")
    with pytest.raises(FileNotFoundError):
        load_documents(tmp_path)  # empty folder


def test_sample_docs_chunk_cleanly():
    chunks = chunk_folder(PROJECT_ROOT / "sample_docs")
    assert {c.source for c in chunks} == {"catering.md", "faq.md", "hours-and-location.md", "menu.md", "policies.md"}
    assert all(c.text.strip() and len(c.text) <= 900 for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)
