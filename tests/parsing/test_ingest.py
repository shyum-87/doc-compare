"""The whole flow, including broken input. Nothing may crash and nothing broken may pass."""

from __future__ import annotations

import hashlib
import logging
from collections import Counter

import pytest

from app.parsing import ingest as ingest_module
from app.parsing.ingest import PARSER_VERSION, ingest

SOURCE_LANGUAGES = ["en", "vi", "zh"]


def _ingest(path, original_language="ko", source_path=None):
    return ingest(
        path,
        doc_id="SOP-SAMPLE",
        version="1",
        original_language=original_language,
        source_path=source_path,
    )


def _codes(result):
    return Counter(finding.code for finding in result.findings)


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


# --- normal input ---------------------------------------------------------------------


def test_a_korean_baseline_document(ko_sample):
    result = _ingest(ko_sample)
    assert result.status == "OK"
    assert result.parser_version == PARSER_VERSION
    assert result.failure is None
    assert result.translation_check is None
    assert _codes(result) == {"IMAGE_PRESENT": 3}

    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.doc_id == "SOP-SAMPLE"
    assert document.version == "1"
    assert document.variant == "source"  # never translated: it is its own source
    assert document.language == "ko"
    assert document.file_name == "sample_bakery_sop.md"
    assert document.sha256 == hashlib.sha256(ko_sample.read_bytes()).hexdigest()
    assert len(document.elements) == 49


@pytest.mark.parametrize("language", SOURCE_LANGUAGES)
def test_a_translated_document_with_its_source(ko_sample, source_samples, language):
    result = _ingest(ko_sample, language, source_samples[language])
    assert result.status == "OK"
    assert _codes(result) == {"IMAGE_PRESENT": 6}

    translated, source = result.documents  # the main file first
    assert (translated.variant, translated.language) == ("translated", "ko")
    assert (source.variant, source.language) == ("source", language)
    assert source.file_name == f"sample_bakery_sop.{language}.md"
    assert source.sha256 == hashlib.sha256(source_samples[language].read_bytes()).hexdigest()
    assert (translated.doc_id, source.doc_id) == ("SOP-SAMPLE", "SOP-SAMPLE")

    assert len(result.translation_check.pairs) == 120
    assert result.translation_check.unpaired == ()


@pytest.mark.parametrize("language", SOURCE_LANGUAGES)
def test_a_translated_document_without_its_source_needs_review(ko_sample, language):
    result = _ingest(ko_sample, language)
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"IMAGE_PRESENT": 3, "SOURCE_NOT_PROVIDED": 1}
    finding = [f for f in result.findings if f.code == "SOURCE_NOT_PROVIDED"][0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    assert finding.element_ids == ()  # it is about the whole document
    assert result.translation_check is None
    assert [document.variant for document in result.documents] == ["translated"]


def test_a_korean_baseline_document_takes_no_source(ko_sample, source_samples):
    with pytest.raises(ValueError):
        _ingest(ko_sample, "ko", source_samples["en"])


def test_a_changed_number_in_the_translation_needs_review(tmp_path, ko_sample, source_samples):
    text = ko_sample.read_text(encoding="utf-8").replace("±1.0%", "±2.0%")
    result = _ingest(_write(tmp_path, "rag_ko.md", text), "vi", source_samples["vi"])
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"IMAGE_PRESENT": 6, "TOKEN_MISMATCH": 1}


def test_bom_and_crlf_are_read_normally(tmp_path, ko_sample):
    text = ko_sample.read_text(encoding="utf-8")
    windows = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
    result = _ingest(_write(tmp_path, "windows.md", windows))
    assert result.status == "OK"
    assert _ingest(ko_sample).documents[0].elements == result.documents[0].elements
    # the hash is taken over the bytes as they are on disk
    assert result.documents[0].sha256 == hashlib.sha256(windows).hexdigest()


# --- broken input ---------------------------------------------------------------------


def _assert_failed(result, reason, document):
    assert result.status == "FAILED"
    assert result.parser_version == PARSER_VERSION
    assert result.failure.reason == reason
    assert result.failure.document == document
    # a failed result carries nothing that could be mistaken for a parsed document
    assert result.documents == ()
    assert result.findings == ()
    assert result.translation_check is None


def test_a_missing_file_fails(tmp_path):
    _assert_failed(_ingest(tmp_path / "missing.md"), "FILE_UNREADABLE", "source")


def test_a_directory_fails(tmp_path):
    _assert_failed(_ingest(tmp_path), "FILE_UNREADABLE", "source")


@pytest.mark.parametrize("data", [b"", b"\n\n  \n", b"\xef\xbb\xbf"])
def test_an_empty_file_fails(tmp_path, data):
    _assert_failed(_ingest(_write(tmp_path, "empty.md", data)), "EMPTY_DOCUMENT", "source")


def test_a_file_that_is_not_utf8_fails(tmp_path):
    path = _write(tmp_path, "cp949.md", "[PAGE 1]\n문단이다.\n".encode("cp949"))
    _assert_failed(_ingest(path), "NOT_UTF8", "source")


def test_a_broken_main_file_of_a_translated_document(tmp_path, source_samples):
    result = _ingest(tmp_path / "missing.md", "en", source_samples["en"])
    _assert_failed(result, "FILE_UNREADABLE", "translated")


@pytest.mark.parametrize(
    "data, reason",
    [(None, "FILE_UNREADABLE"), (b"", "EMPTY_DOCUMENT"), ("문단".encode("cp949"), "NOT_UTF8")],
)
def test_a_broken_source_file_fails_the_whole_result(tmp_path, ko_sample, data, reason):
    source = tmp_path / "rag.md"
    if data is not None:
        source.write_bytes(data)
    # the Korean file is fine, but the result must not look like a normal one
    _assert_failed(_ingest(ko_sample, "vi", source), reason, "source")


def test_a_file_without_page_markers_needs_review(tmp_path):
    result = _ingest(_write(tmp_path, "no_page.md", "## 1 개요\n\n문단이다.\n"))
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"NO_PAGE_MARKER": 1}
    assert len(result.documents[0].elements) == 2  # the elements are still there to review


def test_a_table_row_with_a_wrong_number_of_cells_needs_review(tmp_path):
    text = "[PAGE 1]\n|구분|기준|\n|---|---|\n|온도|2~8℃|냉장|\n"
    result = _ingest(_write(tmp_path, "table.md", text))
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"TABLE_ROW_WIDTH_MISMATCH": 1}


def test_lines_that_fit_no_rule_need_review(tmp_path):
    text = "[PAGE 1]\n<div>문단</div>\n---\n[PAGE x]\n"
    result = _ingest(_write(tmp_path, "odd.md", text))
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"UNCLASSIFIED_LINE": 3}
    assert [element.kind for element in result.documents[0].elements[1:]] == ["unclassified"] * 3


@pytest.mark.parametrize(
    "data",
    [
        b"\x00\x01\x02\x03",
        b"|||||\n|-|\n|",
        b"[PAGE 1]\n" + b"#" * 5000 + b"\n",
        b"[PAGE 99999999999999999999]\n![](<>)\n- \n1)\n",
    ],
)
def test_broken_structure_never_escapes_as_an_exception_or_as_ok(tmp_path, data):
    result = _ingest(_write(tmp_path, "odd.md", data))
    assert result.status in ("FAILED", "REVIEW_REQUIRED")


# --- unexpected errors ----------------------------------------------------------------


def test_an_unexpected_error_fails_closed(monkeypatch, caplog, ko_sample):
    def explode(lines, variant):
        raise RuntimeError("비밀 문장: " + lines[6])

    monkeypatch.setattr(ingest_module, "parse_lines", explode)
    with caplog.at_level(logging.INFO):
        result = _ingest(ko_sample)
    _assert_failed(result, "INTERNAL_ERROR", None)
    assert "RuntimeError" in caplog.text
    assert "비밀 문장" not in caplog.text  # the message may quote the document


def test_a_lost_line_fails_closed(monkeypatch, ko_sample):
    real = ingest_module.parse_lines

    def drop_one(lines, variant):
        elements, findings = real(lines, variant)
        return elements[:-1], findings

    monkeypatch.setattr(ingest_module, "parse_lines", drop_one)
    _assert_failed(_ingest(ko_sample), "INTERNAL_ERROR", None)


def test_an_error_while_checking_the_translation_fails_closed(
    monkeypatch, ko_sample, source_samples
):
    def explode(translated, source):
        raise KeyError("e0001")

    monkeypatch.setattr(ingest_module, "check_translation", explode)
    _assert_failed(_ingest(ko_sample, "en", source_samples["en"]), "INTERNAL_ERROR", None)


# --- logs -----------------------------------------------------------------------------


def test_logs_report_counts_and_codes(caplog, ko_sample, source_samples):
    with caplog.at_level(logging.INFO):
        _ingest(ko_sample, "vi", source_samples["vi"])
    assert "read the translated file: 114 lines, 49 elements" in caplog.text
    assert "read the source file: 114 lines, 49 elements" in caplog.text
    assert "status: OK" in caplog.text
    assert "findings: IMAGE_PRESENT=6" in caplog.text


def test_logs_carry_no_document_text(caplog, tmp_path, ko_sample, source_samples):
    text = ko_sample.read_text(encoding="utf-8").replace("±1.0%", "±2.0%")
    with caplog.at_level(logging.DEBUG):
        result = _ingest(_write(tmp_path, "rag_ko.md", text), "vi", source_samples["vi"])
    assert result.status == "REVIEW_REQUIRED"
    assert "TOKEN_MISMATCH=1" in caplog.text
    for document in result.documents:
        for element in document.elements:
            if element.kind == "page_marker":
                continue
            for line in element.raw.split("\n"):
                assert line not in caplog.text
    for finding in result.findings:
        for token in (*finding.missing_tokens, *finding.extra_tokens):
            assert token not in caplog.text
            assert token.split(":", 1)[1] not in caplog.text


def test_a_read_failure_is_logged_by_its_reason_only(caplog, tmp_path):
    with caplog.at_level(logging.INFO):
        _ingest(_write(tmp_path, "cp949.md", "문단이다.".encode("cp949")))
    assert "cannot read the source file: NOT_UTF8" in caplog.text
