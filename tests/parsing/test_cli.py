"""Command line: python -m app.parsing (spec section 8)."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from app.models.findings import IngestResult
from app.parsing.__main__ import main
from app.parsing.ingest import ingest

ROOT = Path(__file__).resolve().parents[2]


def _args(main_file, out, language="ko", source=None):
    args = [
        str(main_file),
        "--doc-id",
        "SOP-SAMPLE",
        "--version",
        "1",
        "--original-language",
        language,
        "--out",
        str(out),
    ]
    if source is not None:
        args += ["--source", str(source)]
    return args


def _read(out):
    return IngestResult.model_validate_json(out.read_text(encoding="utf-8"))


def test_ok_exits_with_0(tmp_path, ko_sample):
    out = tmp_path / "result.json"
    assert main(_args(ko_sample, out)) == 0
    assert _read(out).status == "OK"


@pytest.mark.parametrize("language", ["en", "vi", "zh"])
def test_a_translated_document_with_its_source_exits_with_0(
    tmp_path, ko_sample, source_samples, language
):
    out = tmp_path / "result.json"
    assert main(_args(ko_sample, out, language, source_samples[language])) == 0
    result = _read(out)
    assert result.status == "OK"
    assert [document.language for document in result.documents] == ["ko", language]
    assert len(result.translation_check.pairs) == 120


def test_review_required_exits_with_1(tmp_path, ko_sample):
    out = tmp_path / "result.json"
    assert main(_args(ko_sample, out, "vi")) == 1  # a translation without its source
    result = _read(out)
    assert result.status == "REVIEW_REQUIRED"
    assert "SOURCE_NOT_PROVIDED" in [finding.code for finding in result.findings]


def test_failed_exits_with_2_and_still_writes_the_result(tmp_path):
    out = tmp_path / "result.json"
    assert main(_args(tmp_path / "missing.md", out)) == 2
    result = _read(out)
    assert result.status == "FAILED"
    assert result.failure.reason == "FILE_UNREADABLE"
    assert result.documents == ()


def test_the_result_file_reads_back_as_the_same_result(tmp_path, ko_sample, source_samples):
    out = tmp_path / "result.json"
    main(_args(ko_sample, out, "zh", source_samples["zh"]))
    expected = ingest(
        ko_sample,
        doc_id="SOP-SAMPLE",
        version="1",
        original_language="zh",
        source_path=source_samples["zh"],
    )
    assert _read(out) == expected


def test_the_result_file_is_utf8_with_lf(tmp_path, ko_sample):
    out = tmp_path / "result.json"
    main(_args(ko_sample, out))
    data = out.read_bytes()
    assert b"\r\n" not in data
    assert "합께".encode("utf-8") in data  # Korean is written as it is, not as \u escapes


def test_the_output_directory_is_created(tmp_path, ko_sample):
    out = tmp_path / "out" / "sample" / "result.json"
    assert main(_args(ko_sample, out)) == 0
    assert out.is_file()


def test_a_result_file_that_cannot_be_written_exits_with_2(tmp_path, ko_sample):
    assert main(_args(ko_sample, tmp_path)) == 2  # --out is a directory


def test_source_with_a_korean_original_is_a_usage_error(tmp_path, ko_sample, source_samples):
    out = tmp_path / "result.json"
    with pytest.raises(SystemExit) as exit_info:
        main(_args(ko_sample, out, "ko", source_samples["en"]))
    assert exit_info.value.code == 2
    assert not out.exists()


@pytest.mark.parametrize(
    "drop",
    ["--doc-id", "--version", "--original-language", "--out"],
)
def test_a_missing_option_is_a_usage_error(tmp_path, ko_sample, drop):
    args = _args(ko_sample, tmp_path / "result.json")
    index = args.index(drop)
    del args[index : index + 2]
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    assert exit_info.value.code == 2


def test_an_unknown_language_is_a_usage_error(tmp_path, ko_sample):
    with pytest.raises(SystemExit) as exit_info:
        main(_args(ko_sample, tmp_path / "result.json", "ja"))
    assert exit_info.value.code == 2


def test_logs_carry_no_document_text(tmp_path, caplog, ko_sample, source_samples):
    out = tmp_path / "result.json"
    with caplog.at_level(logging.INFO):
        main(_args(ko_sample, out, "en", source_samples["en"]))
    assert "status: OK" in caplog.text
    for path in (ko_sample, source_samples["en"]):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("[PAGE"):
                assert line not in caplog.text


def test_run_as_a_module(tmp_path, ko_sample, source_samples):
    out = tmp_path / "result.json"
    command = [sys.executable, "-m", "app.parsing", *_args(ko_sample, out, "vi")]
    done = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    assert done.returncode == 1
    assert done.stdout == b""  # the result goes to the file, the log to stderr
    log = done.stderr.decode("ascii")  # codes and counts only: no Korean text can be in it
    assert "status: REVIEW_REQUIRED" in log
    assert "SOURCE_NOT_PROVIDED=1" in log
    assert _read(out).status == "REVIEW_REQUIRED"

    command = [sys.executable, "-m", "app.parsing", *_args(ko_sample, out, "ko")]
    command += ["--source", str(source_samples["en"])]
    done = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    assert done.returncode == 2
    assert b"--source cannot be used" in done.stderr
