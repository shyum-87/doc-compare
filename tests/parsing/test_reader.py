"""Reading a file into lines: encoding, line endings, hash, expected failures."""

from __future__ import annotations

import hashlib

from app.parsing.reader import read_lines

TEXT = "[PAGE 1]\n\n## 1. 개요\n\n본문이다.\n"


def test_lines_and_hash_of_a_plain_file(tmp_path):
    path = tmp_path / "sample.md"
    path.write_bytes(TEXT.encode("utf-8"))
    result = read_lines(path)
    assert result.error is None
    assert result.file_name == "sample.md"
    assert result.lines == ("[PAGE 1]", "", "## 1. 개요", "", "본문이다.")
    assert result.sha256 == hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


def test_crlf_gives_the_same_lines_as_lf(tmp_path):
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(TEXT.encode("utf-8"))
    crlf.write_bytes(TEXT.replace("\n", "\r\n").encode("utf-8"))
    assert read_lines(crlf).lines == read_lines(lf).lines
    assert read_lines(crlf).sha256 != read_lines(lf).sha256  # the hash is of the raw bytes


def test_a_bom_is_ignored_but_hashed(tmp_path):
    data = b"\xef\xbb\xbf" + TEXT.encode("utf-8")
    path = tmp_path / "bom.md"
    path.write_bytes(data)
    result = read_lines(path)
    assert result.lines[0] == "[PAGE 1]"
    assert result.sha256 == hashlib.sha256(data).hexdigest()


def test_a_missing_last_newline_changes_nothing(tmp_path):
    path = tmp_path / "no_newline.md"
    path.write_bytes(TEXT.rstrip("\n").encode("utf-8"))
    assert read_lines(path).lines == ("[PAGE 1]", "", "## 1. 개요", "", "본문이다.")


def test_a_missing_file_is_unreadable(tmp_path):
    result = read_lines(tmp_path / "nothing.md")
    assert result.error == "FILE_UNREADABLE"
    assert result.sha256 is None
    assert result.lines == ()


def test_a_directory_is_unreadable(tmp_path):
    assert read_lines(tmp_path).error == "FILE_UNREADABLE"


def test_bytes_that_are_not_utf8_are_reported(tmp_path):
    path = tmp_path / "cp949.md"
    path.write_bytes("본문이다.".encode("cp949"))
    result = read_lines(path)
    assert result.error == "NOT_UTF8"
    assert result.lines == ()
    assert result.sha256 is not None


def test_a_file_without_text_is_empty(tmp_path):
    for name, data in [("empty.md", b""), ("blank.md", b"\n  \n\t\r\n")]:
        path = tmp_path / name
        path.write_bytes(data)
        assert read_lines(path).error == "EMPTY_DOCUMENT"
