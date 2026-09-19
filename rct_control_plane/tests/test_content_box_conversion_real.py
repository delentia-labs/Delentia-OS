"""
Real ALGO-23 format-conversion tests — Round 26 Phase 18 Task 38.

Master doc (DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md, section 3, ALGO-23)
specifies Content-Box format conversion (Markdown/HTML/JSON/PDF). The real
`LocalStorageHandler` only did versioned storage + SHA-256 checksums before
this task - zero conversion capability existed. This closes that gap with
real, already-installed libraries (markdown, reportlab) - never a fabricated
conversion.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import io
import json
import asyncio
import tempfile

from rct_control_plane.algo_23_content_box import LocalStorageHandler
from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def _handler():
    tmp = tempfile.mkdtemp(prefix="content_box_conv_test_")
    return LocalStorageHandler(storage_path=tmp)


def test_convert_to_html_produces_real_markdown_rendered_tags():
    handler = _handler()
    text = "# Hello\n\nThis is **bold** text."
    asyncio.run(handler.save("doc1", 1, io.BytesIO(text.encode("utf-8"))))

    result = asyncio.run(handler.convert_content("doc1", 1, target_format="html"))

    assert result["converted"] is True
    assert result["format"] == "html"
    assert "<h1>Hello</h1>" in result["output"]
    assert "<strong>bold</strong>" in result["output"]


def test_convert_to_pdf_produces_a_real_nonzero_pdf_file():
    handler = _handler()
    text = "Line one.\n\nLine two."
    asyncio.run(handler.save("doc2", 1, io.BytesIO(text.encode("utf-8"))))

    result = asyncio.run(handler.convert_content("doc2", 1, target_format="pdf"))

    assert result["converted"] is True
    assert result["format"] == "pdf"
    assert result["size_bytes"] > 0
    with open(result["output_path"], "rb") as f:
        header = f.read(5)
    assert header == b"%PDF-", f"expected a real PDF file, got header {header!r}"


def test_convert_to_json_is_real_valid_json():
    handler = _handler()
    text = "plain content"
    asyncio.run(handler.save("doc3", 1, io.BytesIO(text.encode("utf-8"))))

    result = asyncio.run(handler.convert_content("doc3", 1, target_format="json"))

    assert result["converted"] is True
    assert result["format"] == "json"
    parsed = json.loads(result["output"])
    assert parsed["content_id"] == "doc3"
    assert parsed["version"] == 1
    assert parsed["text"] == text


def test_convert_to_unsupported_format_is_honest_not_fabricated():
    handler = _handler()
    text = "content"
    asyncio.run(handler.save("doc4", 1, io.BytesIO(text.encode("utf-8"))))

    result = asyncio.run(handler.convert_content("doc4", 1, target_format="xml"))

    assert result["converted"] is False
    assert "not supported" in result["reason"]


def test_kernel_algo23_convert_content_wraps_the_real_content_box():
    kernel = AlgorithmKernel41()
    save_result = asyncio.run(kernel.algo_23_content_box("kernel-doc1", 1, b"# Title\n\nBody text."))
    assert save_result["checksum"].startswith("sha256:")

    convert_result = asyncio.run(kernel.algo_23_convert_content("kernel-doc1", 1, target_format="html"))

    assert convert_result["converted"] is True
    assert "<h1>Title</h1>" in convert_result["output"]
