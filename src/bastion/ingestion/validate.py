import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

MAX_BYTES = 10 * 1024 * 1024
MAX_UNZIPPED_BYTES = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 1000

PDF = b"%PDF-"
ZIP = b"PK\x03\x04"
BINARY_SIGNATURES = (PDF, ZIP, b"\x7fELF", b"MZ", b"\x89PNG", b"\xff\xd8\xff", b"GIF8")

TYPES = {
    ".md": ("md", "text/markdown"),
    ".txt": ("txt", "text/plain"),
    ".html": ("html", "text/html"),
    ".json": ("slack", "application/json"),
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}

MISMATCH = "file content does not match its type"


class UploadRejected(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    source_type: str
    media_type: str
    byte_size: int
    sha256: str


def check_text(content: bytes) -> None:
    if content.startswith(BINARY_SIGNATURES) or b"\x00" in content:
        raise UploadRejected(MISMATCH)

    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        raise UploadRejected(MISMATCH) from None


def check_slack(content: bytes) -> None:
    check_text(content)

    try:
        messages = json.loads(content)
    except json.JSONDecodeError:
        raise UploadRejected(MISMATCH) from None

    if not isinstance(messages, list):
        raise UploadRejected(MISMATCH)


def check_pdf(content: bytes) -> None:
    if not content.startswith(PDF):
        raise UploadRejected(MISMATCH)


def check_docx(content: bytes) -> None:
    if not content.startswith(ZIP):
        raise UploadRejected(MISMATCH)

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
    except zipfile.BadZipFile:
        raise UploadRejected(MISMATCH) from None

    if len(entries) > MAX_ZIP_ENTRIES or sum(e.file_size for e in entries) > MAX_UNZIPPED_BYTES:
        raise UploadRejected("file expands to more than is allowed")

    if "word/document.xml" not in {entry.filename for entry in entries}:
        raise UploadRejected(MISMATCH)


CHECKS = {
    "md": check_text,
    "txt": check_text,
    "html": check_text,
    "slack": check_slack,
    "pdf": check_pdf,
    "docx": check_docx,
}


def validate_upload(filename: str, content: bytes) -> ValidatedUpload:
    suffix = PurePosixPath(filename).suffix.lower()

    if suffix not in TYPES:
        raise UploadRejected("file type is not supported")
    if not content:
        raise UploadRejected("file is empty")
    if len(content) > MAX_BYTES:
        raise UploadRejected("file is larger than 10 MB")

    source_type, media_type = TYPES[suffix]
    CHECKS[source_type](content)

    return ValidatedUpload(
        source_type, media_type, len(content), hashlib.sha256(content).hexdigest()
    )