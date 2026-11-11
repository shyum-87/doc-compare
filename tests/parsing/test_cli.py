"""Command line: python -m app.parsing (spec section 8)."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import get_args

import pytest

from app.models.document import Language
from app.models.findings import IngestResult, Status
from app.parsing.__main__ import EXIT_CODES, build_parser, main
from app.parsing.ingest import ingest

ROOT = Path(__file__).resolve().parents[2]

# what ingest logs for the Korean sample read as a translation, with its source
RUN_LOG = [
    ("app.parsing.ingest", "INFO", "read the translated file: 114 lines, 49 elements"),
    ("app.parsing.ingest", "INFO", "read the source file: 114 lines, 49 elements"),
    ("app.parsing.ingest", "INFO", "status: OK"),
    ("app.parsing.ingest", "INFO", "findings: IMAGE_PRESENT=6"),
]
# the same sample read as a translation without its source
REVIEW_LOG = [
    ("app.parsing.ingest", "INFO", "read the translated file: 114 lines, 49 elements"),
    ("app.parsing.ingest", "INFO", "status: REVIEW_REQUIRED"),
    ("app.parsing.ingest", "INFO", "findings: IMAGE_PRESENT=3, SOURCE_NOT_PROVIDED=1"),
]
# a translated file that is not there
FAILED_LOG = [
    ("app.parsing.ingest", "ERROR", "cannot read the translated file: FILE_UNREADABLE"),
]


class Odd(Exception):
    """An error of no built-in type: every Exception is caught, not a list of types."""


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


def _records(caplog):
    return [(record.name, record.levelname, record.getMessage()) for record in caplog.records]


def _usage_error(args):
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    return exit_info.value.code


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


def test_every_status_has_an_exit_code():
    assert set(EXIT_CODES) == set(get_args(Status))


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


def test_an_older_result_file_is_replaced(tmp_path, ko_sample):
    out = tmp_path / "result.json"
    out.write_text("an older result", encoding="utf-8")
    assert main(_args(ko_sample, out)) == 0
    assert _read(out).status == "OK"


def test_a_result_file_that_cannot_be_written_exits_with_2(tmp_path, caplog, ko_sample):
    with caplog.at_level(logging.DEBUG):
        assert main(_args(ko_sample, tmp_path)) == 2  # --out is a directory
    name, level, message = _records(caplog)[-1]
    assert (name, level) == ("app.parsing", "ERROR")
    assert message in (
        "cannot write the result file: PermissionError",  # Windows
        "cannot write the result file: IsADirectoryError",
    )


def test_an_output_directory_that_cannot_be_made_exits_with_2(tmp_path, caplog, ko_sample):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the directory should be", encoding="utf-8")
    with caplog.at_level(logging.DEBUG):
        assert main(_args(ko_sample, blocker / "result.json")) == 2
    assert _records(caplog)[-1] == (
        "app.parsing",
        "ERROR",
        "cannot write the result file: FileExistsError",
    )
    assert blocker.read_text(encoding="utf-8") == "a file where the directory should be"


@pytest.mark.parametrize("error", [OSError, RuntimeError, ValueError, Odd])
def test_any_error_while_writing_exits_with_2_and_logs_its_type_only(
    tmp_path, caplog, capsys, monkeypatch, ko_sample, source_samples, error
):
    def explode(self, data):
        raise error(f"비밀 문장 {self}")

    monkeypatch.setattr(Path, "write_bytes", explode)
    out = tmp_path / "result.json"
    with caplog.at_level(logging.DEBUG):
        assert main(_args(ko_sample, out, "en", source_samples["en"])) == 2
    assert _records(caplog) == [
        *RUN_LOG,
        ("app.parsing", "ERROR", f"cannot write the result file: {error.__name__}"),
    ]
    assert "비밀 문장" not in caplog.text  # no message and no traceback of the error
    assert "비밀 문장" not in capsys.readouterr().err  # and none printed past the log
    assert not out.exists()


def test_an_unexpected_error_exits_with_2_and_logs_its_type_only(
    tmp_path, caplog, capsys, monkeypatch, ko_sample
):
    def explode(*args, **kwargs):
        raise Odd("비밀 문장")

    monkeypatch.setattr("app.parsing.__main__.ingest", explode)
    out = tmp_path / "result.json"
    with caplog.at_level(logging.DEBUG):
        assert main(_args(ko_sample, out)) == 2  # not 1: no result file says what to review
    assert _records(caplog) == [("app.parsing", "ERROR", "internal error: Odd")]
    assert "비밀 문장" not in caplog.text
    assert "비밀 문장" not in capsys.readouterr().err
    assert not out.exists()


def test_a_result_that_cannot_be_turned_into_json_exits_with_2(tmp_path, caplog, ko_sample):
    args = _args(ko_sample, tmp_path / "result.json")
    args[args.index("--doc-id") + 1] = "SOP-" + chr(0xD800)  # half a surrogate pair: not UTF-8
    with caplog.at_level(logging.DEBUG):
        assert main(args) == 2
    name, level, message = _records(caplog)[-1]
    assert (name, level) == ("app.parsing", "ERROR")
    assert message.startswith("internal error: ")
    assert not (tmp_path / "result.json").exists()


def test_an_interrupt_is_not_turned_into_an_exit_code(tmp_path, monkeypatch, ko_sample):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("app.parsing.__main__.ingest", interrupt)
    with pytest.raises(KeyboardInterrupt):
        main(_args(ko_sample, tmp_path / "result.json"))


def test_source_with_a_korean_original_is_a_usage_error(tmp_path, ko_sample, source_samples):
    out = tmp_path / "result.json"
    assert _usage_error(_args(ko_sample, out, "ko", source_samples["en"])) == 2
    assert not out.exists()


def _copy(path, directory):
    copy = directory / path.name
    copy.write_bytes(path.read_bytes())
    return copy


def test_out_naming_the_main_file_is_a_usage_error(tmp_path, ko_sample):
    main_file = _copy(ko_sample, tmp_path)
    (tmp_path / "sub").mkdir()
    for out in (main_file, tmp_path / "sub" / ".." / main_file.name):
        assert _usage_error(_args(main_file, out)) == 2
        assert main_file.read_bytes() == ko_sample.read_bytes()  # the document is still there


def test_out_naming_the_source_file_is_a_usage_error(tmp_path, ko_sample, source_samples):
    main_file = _copy(ko_sample, tmp_path)
    source = _copy(source_samples["vi"], tmp_path)
    assert _usage_error(_args(main_file, source, "vi", source)) == 2
    assert main_file.read_bytes() == ko_sample.read_bytes()
    assert source.read_bytes() == source_samples["vi"].read_bytes()


def test_out_naming_a_missing_main_file_is_a_usage_error(tmp_path):
    missing = tmp_path / "missing.md"
    for out in (missing, tmp_path / "sub" / ".." / "missing.md"):
        assert _usage_error(_args(missing, out)) == 2
        assert not missing.exists()  # no result is written where the document was expected


def test_out_is_compared_as_a_file_and_not_as_a_spelling(tmp_path, monkeypatch, ko_sample):
    # a hard link or a short name of the main file: only the operating system can tell
    monkeypatch.setattr(Path, "samefile", lambda self, other: True)
    out = tmp_path / "result.json"
    assert _usage_error(_args(ko_sample, out)) == 2
    assert not out.exists()


@pytest.mark.parametrize(
    "drop",
    ["--doc-id", "--version", "--original-language", "--out"],
)
def test_a_missing_option_is_a_usage_error(tmp_path, ko_sample, drop):
    args = _args(ko_sample, tmp_path / "result.json")
    index = args.index(drop)
    del args[index : index + 2]
    assert _usage_error(args) == 2


def test_an_unknown_language_is_a_usage_error(tmp_path, ko_sample):
    assert _usage_error(_args(ko_sample, tmp_path / "result.json", "ja")) == 2


def test_the_languages_are_those_of_the_document_model(tmp_path, ko_sample):
    assert "{" + ",".join(get_args(Language)) + "}" in build_parser().format_usage()  # no other
    for language in get_args(Language):
        args = build_parser().parse_args(_args(ko_sample, tmp_path / "result.json", language))
        assert args.original_language == language


@pytest.mark.parametrize("status", get_args(Status))
def test_the_log_of_a_run_holds_counts_and_codes_only(
    tmp_path, caplog, ko_sample, source_samples, status
):
    out = tmp_path / "result.json"
    args, expected = {
        "OK": (_args(ko_sample, out, "en", source_samples["en"]), RUN_LOG),
        "REVIEW_REQUIRED": (_args(ko_sample, out, "vi"), REVIEW_LOG),
        "FAILED": (_args(tmp_path / "missing.md", out, "vi"), FAILED_LOG),
    }[status]
    with caplog.at_level(logging.DEBUG):
        assert main(args) == EXIT_CODES[status]
    # the whole log: a line with a path, a document ID or text of a document would show here
    assert _records(caplog) == expected


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
