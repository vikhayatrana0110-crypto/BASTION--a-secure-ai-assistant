import hashlib
import io
import zipfile

import pytest

from bastion.ingestion import validate
from bastion.ingestion.validate import TYPES, UploadRejected, validate_upload


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)

    return buffer.getvalue()


DOCX = zip_bytes({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>"})


def test_a_markdown_file_is_accepted_and_described():
    content = b"# Title\n\nSome text."

    upload = validate_upload("handbook.md", content)

    assert upload.source_type == "md"
    assert upload.media_type == "text/markdown"
    assert upload.byte_size == len(content)
    assert upload.sha256 == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize(
    "filename, content, source_type",
    [
        ("notes.txt", b"plain text", "txt"),
        ("page.html", b"<html><body>hi</body></html>", "html"),
        ("export.json", b'[{"user": "U1", "text": "hello"}]', "slack"),
        ("report.pdf", b"%PDF-1.7\n...", "pdf"),
        ("policy.docx", DOCX, "docx"),
        ("SHOUTING.MD", b"# Loud", "md"),
    ],
)
def test_each_supported_type_is_accepted(filename, content, source_type):
    assert validate_upload(filename, content).source_type == source_type


@pytest.mark.parametrize("filename", ["tool.exe", "archive.zip", "report.pdf.exe", "no_extension"])
def test_an_unsupported_file_type_is_rejected(filename):
    with pytest.raises(UploadRejected, match="not supported"):
        validate_upload(filename, b"anything")


def test_an_empty_file_is_rejected():
    with pytest.raises(UploadRejected, match="empty"):
        validate_upload("empty.md", b"")


def test_a_file_over_the_size_limit_is_rejected(monkeypatch):
    monkeypatch.setattr(validate, "MAX_BYTES", 10)

    with pytest.raises(UploadRejected, match="larger"):
        validate_upload("big.md", b"12345678901")


@pytest.mark.parametrize(
    "filename, content",
    [
        ("renamed.md", b"%PDF-1.7 really a pdf"),
        ("renamed.txt", b"MZ\x90\x00 really an executable"),
        ("renamed.html", DOCX),
        ("binary.md", b"text with a \x00 null byte"),
        ("latin1.md", "caf\xe9".encode("latin-1")),
        ("fake.pdf", b"this is not a pdf"),
        ("fake.docx", b"this is not a zip"),
        ("zip-not-word.docx", zip_bytes({"readme.txt": b"hello"})),
        ("broken.docx", b"PK\x03\x04 truncated"),
        ("object.json", b'{"not": "a list"}'),
        ("invalid.json", b"[not json"),
    ],
)
def test_content_that_does_not_match_the_type_is_rejected(filename, content):
    with pytest.raises(UploadRejected, match="does not match"):
        validate_upload(filename, content)


def test_a_docx_that_expands_too_much_is_rejected(monkeypatch):
    monkeypatch.setattr(validate, "MAX_UNZIPPED_BYTES", 1000)
    bomb = zip_bytes({"word/document.xml": b"\x00" * 5000})

    assert len(bomb) < 1000

    with pytest.raises(UploadRejected, match="expands"):
        validate_upload("bomb.docx", bomb)


def test_a_docx_with_too_many_entries_is_rejected(monkeypatch):
    monkeypatch.setattr(validate, "MAX_ZIP_ENTRIES", 3)
    crowded = zip_bytes({"word/document.xml": b"x", "a": b"", "b": b"", "c": b""})

    with pytest.raises(UploadRejected, match="expands"):
        validate_upload("crowded.docx", crowded)


def test_every_supported_type_has_a_content_check():
    assert {source_type for source_type, _ in TYPES.values()} == set(validate.CHECKS)