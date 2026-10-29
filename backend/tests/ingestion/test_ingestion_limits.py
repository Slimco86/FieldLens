"""IN-7 byte/file limits at the exact boundary and +1, driven through the streaming receiver
with on-demand generated bodies (no large buffers) and through the API with lowered limits."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import anyio
import pytest
from sqlalchemy.engine import URL

from fieldlens.config import MAX_BATCH_BYTES, MAX_FILE_BYTES, MAX_FILES, MAX_OVERHEAD_BYTES
from fieldlens.contracts.errors import ContractError
from fieldlens.ingestion.upload import UploadLimits, check_content_length, receive_upload
from tests.upload_support import PDF, make_api

MIB = 1024 * 1024
LIMITS = UploadLimits(MAX_FILE_BYTES, MAX_BATCH_BYTES, MAX_FILES, MAX_OVERHEAD_BYTES)
BOUNDARY = "xBOUNDARYx"
CONTENT_TYPE = f"multipart/form-data; boundary={BOUNDARY}"


def _pdf_chunks(size: int) -> AsyncIterator[bytes]:
    async def gen() -> AsyncIterator[bytes]:
        head = b"%PDF-1.7\n"[: min(size, 9)]
        yield head
        left = size - len(head)
        block = bytes(MIB)
        while left > 0:
            n = min(left, MIB)
            yield block[:n]
            left -= n

    return gen()


def body(sizes: list[int], files_meta: int | None = None) -> AsyncIterator[bytes]:
    meta = json.dumps(
        {
            "expected_parent_source_revision_id": None,
            "files": [{} for _ in range(files_meta if files_meta is not None else len(sizes))],
        }
    ).encode()

    async def gen() -> AsyncIterator[bytes]:
        yield (
            (
                f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="metadata"\r\n'
                "Content-Type: application/json\r\n\r\n"
            ).encode()
            + meta
            + b"\r\n"
        )
        for i, size in enumerate(sizes):
            yield (
                f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="files"; '
                f'filename="f{i}.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
            ).encode()
            async for chunk in _pdf_chunks(size):
                yield chunk
            yield b"\r\n"
        yield f"--{BOUNDARY}--\r\n".encode()

    return gen()


def run_receive(tmp_path: Path, sizes: list[int], **kw: int) -> object:
    staging = tmp_path / "s"
    staging.mkdir(parents=True)

    async def go() -> object:
        return await receive_upload(
            body(sizes, kw.get("files_meta")), CONTENT_TYPE, staging, LIMITS
        )

    return anyio.run(go)


def reason_of(exc: ContractError) -> str:
    assert exc.details is not None
    return str(exc.details["reason"])


def test_limit_constants_are_the_approved_values() -> None:
    assert (MAX_FILE_BYTES, MAX_BATCH_BYTES, MAX_FILES) == (128 * MIB, 512 * MIB, 200)


def test_file_exactly_at_limit_is_accepted(tmp_path: Path) -> None:
    received = run_receive(tmp_path, [MAX_FILE_BYTES])
    assert received.files[0].size == MAX_FILE_BYTES  # type: ignore[attr-defined]


def test_file_one_byte_over_limit_is_413(tmp_path: Path) -> None:
    with pytest.raises(ContractError) as exc:
        run_receive(tmp_path, [MAX_FILE_BYTES + 1])
    assert exc.value.status_code == 413 and reason_of(exc.value) == "file_bytes"


def test_batch_exactly_at_limit_is_accepted(tmp_path: Path) -> None:
    received = run_receive(tmp_path, [MAX_FILE_BYTES] * 4)
    assert received.counted_bytes == MAX_BATCH_BYTES  # type: ignore[attr-defined]


def test_batch_one_byte_over_limit_is_413(tmp_path: Path) -> None:
    sizes = [MAX_FILE_BYTES] * 3 + [MAX_FILE_BYTES - 4, 5]
    assert sum(sizes) == MAX_BATCH_BYTES + 1
    with pytest.raises(ContractError) as exc:
        run_receive(tmp_path, sizes)
    assert exc.value.status_code == 413 and reason_of(exc.value) == "batch_bytes"


def test_exactly_200_files_ok_and_201_is_413(tmp_path: Path) -> None:
    received = run_receive(tmp_path, [len(PDF)] * 200)
    assert len(received.files) == 200  # type: ignore[attr-defined]
    with pytest.raises(ContractError) as exc:
        run_receive(tmp_path / "again", [len(PDF)] * 201)
    assert exc.value.status_code == 413 and reason_of(exc.value) == "file_count"


def test_declared_content_length_over_request_limit_is_rejected_early() -> None:
    check_content_length(str(LIMITS.max_request_bytes), LIMITS)
    with pytest.raises(ContractError) as exc:
        check_content_length(str(LIMITS.max_request_bytes + 1), LIMITS)
    assert exc.value.status_code == 413
    with pytest.raises(ContractError):
        check_content_length("abc", LIMITS)


def test_api_enforces_lowered_limits_exactly(migrated_url: URL, tmp_path: Path) -> None:
    size = 1024
    api = make_api(
        migrated_url,
        tmp_path,
        upload_max_file_bytes=size,
        upload_max_batch_bytes=2 * size,
        upload_max_files=3,
    )
    pid = api.project()

    def pdf(n: int, tag: str) -> bytes:
        return (PDF + tag.encode()).ljust(n, b"0")

    over = api.upload(pid, [("a.pdf", pdf(size + 1, "a"))])
    assert over.status_code == 413 and over.json()["error"]["details"]["reason"] == "file_bytes"
    batch = api.upload(
        pid, [("a.pdf", pdf(size, "a")), ("b.pdf", pdf(size, "b")), ("c.pdf", pdf(8 * 3, "c"))]
    )
    assert batch.status_code == 413 and batch.json()["error"]["details"]["reason"] == "batch_bytes"
    many = api.upload(pid, [(f"{i}.pdf", pdf(40, str(i))) for i in range(4)])
    assert many.status_code == 413 and many.json()["error"]["details"]["reason"] == "file_count"
    assert api.blob_files() == [] and not any((tmp_path / "staging").iterdir())
    ok = api.upload(pid, [("a.pdf", pdf(size, "a")), ("b.pdf", pdf(size, "b"))])
    assert ok.status_code == 202, ok.text
    assert api.client.get(f"/api/v1/projects/{pid}").json()["latest_source_revision_id"] is None


def test_settings_cannot_raise_limits_above_approved_values() -> None:
    from pydantic import ValidationError

    from tests.conftest import settings_for

    for field, value in (
        ("upload_max_file_bytes", MAX_FILE_BYTES + 1),
        ("upload_max_batch_bytes", MAX_BATCH_BYTES + 1),
        ("upload_max_files", MAX_FILES + 1),
    ):
        with pytest.raises(ValidationError):
            settings_for(**{field: value})


def test_pdf_page_limit_is_deferred_to_task_009() -> None:
    pytest.skip("500-page PDF limit needs a parser (TASK-009); not claimed by TASK-006")
