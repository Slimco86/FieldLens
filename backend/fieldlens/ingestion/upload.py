"""Streaming multipart intake: bytes are hashed and written to server-named staging files.

Limits are enforced on actually streamed counts (not only ``Content-Length``) so exact-limit
and limit+1 byte requests behave deterministically. Hashing, writing and inspection run in
worker threads, never on the event loop. Nothing is published here: callers receive staged
files and decide publication only after every file has passed inspection.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio.to_thread
from pydantic import ValidationError
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import (
    MultipartParser,
    parse_options_header,
)

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.imports import ImportMetadata
from fieldlens.ingestion.inspect import Detected, inspect_file, reject, validate_filename

FLUSH_BYTES = 256 * 1024
METADATA_MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class UploadLimits:
    max_file_bytes: int
    max_batch_bytes: int
    max_files: int
    max_overhead_bytes: int

    @property
    def max_request_bytes(self) -> int:
        return self.max_batch_bytes + self.max_overhead_bytes


@dataclass
class StagedFile:
    index: int
    filename: str
    path: Path
    sha256: str
    size: int
    detected: Detected


@dataclass
class ReceivedUpload:
    metadata: ImportMetadata
    files: list[StagedFile] = field(default_factory=list)
    counted_bytes: int = 0
    """Streamed file bytes plus archive-expanded bytes (both count against the batch limit)."""


class _Sink:
    """One open staging file; writes happen in a thread so the event loop never hashes/writes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._hash = hashlib.sha256()
        self.size = 0
        self._buffer = bytearray()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._handle = os.fdopen(fd, "wb")

    def _write(self, data: bytes) -> None:
        self._handle.write(data)
        self._hash.update(data)

    async def feed(self, data: bytes) -> None:
        self._buffer += data
        self.size += len(data)
        if len(self._buffer) >= FLUSH_BYTES:
            await self._flush()

    async def _flush(self) -> None:
        if self._buffer:
            chunk = bytes(self._buffer)
            self._buffer.clear()
            await anyio.to_thread.run_sync(self._write, chunk)

    async def finish(self) -> str:
        await self._flush()
        await anyio.to_thread.run_sync(self._close)
        return self._hash.hexdigest()

    def _close(self) -> None:
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()

    def abort(self) -> None:
        try:
            self._handle.close()
        except OSError:
            pass


def _too_large(reason: str, limit: int, message: str) -> ContractError:
    return reject(413, ErrorCode.PAYLOAD_TOO_LARGE, reason, message, limit=limit)


def _malformed(reason: str, message: str) -> ContractError:
    return reject(422, ErrorCode.VALIDATION_ERROR, reason, message)


def check_content_length(header: str | None, limits: UploadLimits) -> None:
    if header is None:
        return
    try:
        declared = int(header)
    except ValueError as exc:
        raise _malformed("bad_content_length", "Content-Length is not a number") from exc
    if declared < 0:
        raise _malformed("bad_content_length", "Content-Length is not valid")
    if declared > limits.max_request_bytes:
        raise _too_large("request_bytes", limits.max_request_bytes, "request body is too large")


def boundary_of(content_type: str | None) -> bytes:
    if not content_type:
        raise reject(
            415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "not_multipart", "multipart/form-data required"
        )
    kind, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if kind != b"multipart/form-data" or not boundary:
        raise reject(
            415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "not_multipart", "multipart/form-data required"
        )
    return boundary


class _Part:
    def __init__(self) -> None:
        self.headers: dict[bytes, bytes] = {}
        self.field = b""
        self.value = b""
        self.name: str | None = None
        self.filename: str | None = None
        self.sink: _Sink | None = None
        self.meta = bytearray()
        self.is_file = False
        self.file_bytes = 0


async def receive_upload(
    stream: AsyncIterator[bytes],
    content_type: str | None,
    staging: Path,
    limits: UploadLimits,
) -> ReceivedUpload:
    """Parse, bound, hash and inspect an upload. Raises typed ``ContractError``s."""
    boundary = boundary_of(content_type)
    events: list[tuple[str, Any]] = []

    callbacks: Any = {
        "on_part_begin": lambda: events.append(("begin", None)),
        "on_header_field": lambda d, s, e: events.append(("hfield", d[s:e])),
        "on_header_value": lambda d, s, e: events.append(("hvalue", d[s:e])),
        "on_header_end": lambda: events.append(("hend", None)),
        "on_headers_finished": lambda: events.append(("hdone", None)),
        "on_part_data": lambda d, s, e: events.append(("data", d[s:e])),
        "on_part_end": lambda: events.append(("end", None)),
    }
    try:
        parser = MultipartParser(boundary, callbacks, max_header_count=8, max_header_size=4224)
    except Exception as exc:  # invalid boundary
        raise _malformed("bad_boundary", "multipart boundary is not valid") from exc

    received: ReceivedUpload | None = None
    metadata_seen = False
    part: _Part | None = None
    total_body = 0
    file_bytes_total = 0
    result_files: list[StagedFile] = []
    expanded_total = 0
    metadata: ImportMetadata | None = None
    open_sink: _Sink | None = None

    async def finish_file(p: _Part) -> None:
        nonlocal expanded_total, open_sink
        assert p.sink is not None and p.filename is not None and metadata is not None
        sha = await p.sink.finish()
        open_sink = None
        remaining = limits.max_batch_bytes - file_bytes_total - expanded_total
        detected = await anyio.to_thread.run_sync(
            lambda: inspect_file(
                p.sink.path,  # type: ignore[union-attr]
                p.filename,  # type: ignore[arg-type]
                max_file_bytes=limits.max_file_bytes,
                remaining_batch_bytes=remaining,
            )
        )
        expanded_total += detected.expanded_bytes
        result_files.append(
            StagedFile(len(result_files), p.filename, p.sink.path, sha, p.sink.size, detected)
        )

    try:
        async for chunk in stream:
            total_body += len(chunk)
            if total_body > limits.max_request_bytes:
                raise _too_large(
                    "request_bytes", limits.max_request_bytes, "request body is too large"
                )
            try:
                parser.write(chunk)
            except MultipartParseError as exc:
                raise _malformed("malformed_multipart", "multipart body is malformed") from exc
            batch = list(events)
            events.clear()
            for kind, payload in batch:
                if kind == "begin":
                    part = _Part()
                elif part is None:
                    continue
                elif kind == "hfield":
                    part.field += payload
                elif kind == "hvalue":
                    part.value += payload
                elif kind == "hend":
                    part.headers[part.field.lower()] = part.value
                    part.field = b""
                    part.value = b""
                elif kind == "hdone":
                    disposition = part.headers.get(b"content-disposition")
                    if disposition is None:
                        raise _malformed("bad_part", "multipart part has no Content-Disposition")
                    _, params = parse_options_header(disposition)
                    try:
                        part.name = params.get(b"name", b"").decode("utf-8")
                        raw_name = params.get(b"filename")
                        part.filename = raw_name.decode("utf-8") if raw_name is not None else None
                    except UnicodeDecodeError as exc:
                        raise _malformed("bad_part", "part header is not valid UTF-8") from exc
                    if not metadata_seen:
                        if part.name != "metadata" or part.filename is not None:
                            raise _malformed(
                                "metadata_first", "the first multipart part must be 'metadata'"
                            )
                    elif part.name != "files" or part.filename is None:
                        raise _malformed(
                            "unexpected_part", "after 'metadata' only 'files' parts are accepted"
                        )
                    if metadata_seen:
                        assert metadata is not None
                        index = len(result_files)
                        if index >= limits.max_files:
                            raise _too_large("file_count", limits.max_files, "too many files")
                        if index >= len(metadata.files):
                            raise _malformed(
                                "file_count_mismatch", "more files than metadata.files entries"
                            )
                        part.is_file = True
                        validate_filename(part.filename or "")
                        part.sink = open_sink = _Sink(staging / f"{index}.part")
                elif kind == "data":
                    if part.is_file:
                        assert part.sink is not None
                        part.file_bytes += len(payload)
                        file_bytes_total += len(payload)
                        if part.file_bytes > limits.max_file_bytes:
                            raise _too_large(
                                "file_bytes", limits.max_file_bytes, "file exceeds the size limit"
                            )
                        if file_bytes_total + expanded_total > limits.max_batch_bytes:
                            raise _too_large(
                                "batch_bytes",
                                limits.max_batch_bytes,
                                "batch exceeds the size limit",
                            )
                        await part.sink.feed(payload)
                    else:
                        part.meta += payload
                        if len(part.meta) > METADATA_MAX_BYTES:
                            raise _too_large(
                                "metadata_bytes", METADATA_MAX_BYTES, "metadata part is too large"
                            )
                elif kind == "end":
                    if part.is_file:
                        await finish_file(part)
                    else:
                        try:
                            metadata = ImportMetadata.model_validate_json(bytes(part.meta))
                        except ValidationError as exc:
                            if any(
                                e["type"] == "too_long" and tuple(e["loc"]) == ("files",)
                                for e in exc.errors()
                            ):
                                raise _too_large(
                                    "file_count", limits.max_files, "too many files"
                                ) from exc
                            raise ContractError(
                                ErrorCode.VALIDATION_ERROR,
                                "import metadata failed validation",
                                422,
                                {
                                    "reason": "bad_metadata",
                                    "errors": [
                                        {"loc": [str(p) for p in e["loc"]], "type": e["type"]}
                                        for e in exc.errors()
                                    ],
                                },
                            ) from exc
                        metadata_seen = True
                        if len(metadata.files) > limits.max_files:
                            raise _too_large("file_count", limits.max_files, "too many files")
                    part = None
            overhead = total_body - file_bytes_total
            if overhead > limits.max_overhead_bytes:
                raise _too_large(
                    "multipart_overhead", limits.max_overhead_bytes, "multipart overhead too large"
                )
        try:
            parser.finalize()
        except MultipartParseError as exc:
            raise _malformed("malformed_multipart", "multipart body is incomplete") from exc
        if parser.state.name != "END":
            raise _malformed("malformed_multipart", "multipart body is incomplete")
        if metadata is None:
            raise _malformed("metadata_first", "the 'metadata' part is required")
        if len(result_files) != len(metadata.files):
            raise _malformed(
                "file_count_mismatch", "number of files differs from metadata.files entries"
            )
        received = ReceivedUpload(
            metadata=metadata,
            files=result_files,
            counted_bytes=file_bytes_total + expanded_total,
        )
        return received
    except BaseException:
        if open_sink is not None:
            open_sink.abort()
        raise
