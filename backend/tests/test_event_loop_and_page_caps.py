"""
Two worker-capacity protections:

  * extract_text_from_upload parses in a worker thread, not on the event loop
    (a slow PDF/DOCX parse used to freeze every other request).
  * the JD requirements extractor reads at most MAX_JD_PDF_PAGES pages, so a
    huge PDF can't occupy the single Celery worker for minutes.
"""

import asyncio
import contextlib
import threading
from types import SimpleNamespace

from app.core import jd_requirements_extractor as jd
from app.core import text_extract


def test_upload_text_extraction_runs_off_the_event_loop(monkeypatch):
    seen = {}

    def fake_extract(raw, filename):
        seen["thread"] = threading.current_thread()
        return "x" * 100

    monkeypatch.setattr(text_extract, "extract_text_from_bytes", fake_extract)

    class FakeUpload:
        filename = "jd.pdf"

        async def read(self):
            return b"%PDF-1.4 fake"

    async def run():
        loop_thread = threading.current_thread()
        text = await text_extract.extract_text_from_upload(FakeUpload())
        return loop_thread, text

    loop_thread, text = asyncio.run(run())
    assert text == "x" * 100
    assert seen["thread"] is not loop_thread


def test_upload_parser_errors_still_become_http_errors(monkeypatch):
    import pytest
    from fastapi import HTTPException

    class FakeUpload:
        filename = "jd.txt"

        async def read(self):
            return b"short"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(text_extract.extract_text_from_upload(FakeUpload()))
    assert exc.value.status_code == 422  # EmptyExtractionError -> 422, via the thread


def test_jd_pdf_pages_are_capped(monkeypatch, tmp_path):
    pdf_file = tmp_path / "huge_jd.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 placeholder")

    pages = [SimpleNamespace(width=612.0) for _ in range(40)]
    fake_pdf = SimpleNamespace(pages=pages)

    @contextlib.contextmanager
    def fake_open(_path):
        yield fake_pdf

    seen_pages = []

    def fake_words(page):
        seen_pages.append(page)
        return []

    monkeypatch.setattr(jd.pdfplumber, "open", fake_open)
    monkeypatch.setattr(jd, "extract_page_words", fake_words)
    monkeypatch.setattr(jd, "detect_page_column_layout", lambda *a, **k: None)
    monkeypatch.setattr(jd, "build_visual_segments", lambda *a, **k: [])
    monkeypatch.setattr(jd, "locate_requirements_heading_on_page", lambda *a, **k: None)
    monkeypatch.setattr(jd, "locate_heading_by_words", lambda *a, **k: None)
    monkeypatch.setattr(jd, "locate_heading_plain_text", lambda *a, **k: None)

    result = jd.extract_requirements_section_from_pdf(pdf_file)

    assert len(seen_pages) == jd.MAX_JD_PDF_PAGES == 10
    assert result["found"] is False
