"""Original-file storage outside the database: staging, atomic no-overwrite publish, verification.

Layout under ``storage_root``::

    staging/<batch-uuid>/<n>.part                 temporary, per request, removed afterwards
    projects/<project-uuid>/blobs/<sha[:2]>/<sha256>   immutable originals (mode 0444)

Blobs are keyed by *project* and hash, so a hash match in another project never reaches
another project's bytes. Published blobs are never deleted by retry cleanup.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import UUID

CHUNK_BYTES = 1024 * 1024
_KEY = re.compile(r"^projects/[0-9a-f-]{36}/blobs/[0-9a-f]{2}/[0-9a-f]{64}$")


class VerifyOutcome(StrEnum):
    OK = "ok"
    MISSING = "missing"
    SIZE_MISMATCH = "size_mismatch"
    HASH_MISMATCH = "hash_mismatch"


@dataclass(frozen=True)
class VerifyResult:
    outcome: VerifyOutcome
    actual_size: int | None = None


def blob_key(project_id: UUID, sha256: str) -> str:
    return f"projects/{project_id}/blobs/{sha256[:2]}/{sha256}"


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def new_staging_dir(self, batch_id: UUID) -> Path:
        path = self.root / "staging" / str(batch_id)
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
        return path

    def remove_staging(self, path: Path) -> None:
        staging_root = (self.root / "staging").resolve()
        resolved = path.resolve()
        if resolved.parent == staging_root:  # never remove anything but a staging child
            shutil.rmtree(resolved, ignore_errors=True)

    def path_for(self, key: str) -> Path:
        """Resolve a server-generated key; any other shape (paths from clients) is refused."""
        if not _KEY.fullmatch(key):
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("storage key escapes the storage root")
        return path

    def publish(self, staged: Path, key: str) -> bool:
        """Link a fully written, fsynced staged file to its immutable key and drop the staging
        name. Never overwrites: returns False when the identical-hash blob already exists."""
        target = self.path_for(key)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        created = True
        try:
            os.link(staged, target)
        except FileExistsError:
            created = False
        if created:
            os.chmod(target, 0o444)
            _fsync_dir(target.parent)
        staged.unlink(missing_ok=True)
        return created

    def verify(self, key: str, sha256: str, size: int) -> VerifyResult:
        """Re-read the stored bytes and compare size and SHA-256 (byte verification only)."""
        try:
            path = self.path_for(key)
            digest = hashlib.sha256()
            actual = 0
            with path.open("rb") as handle:
                while chunk := handle.read(CHUNK_BYTES):
                    actual += len(chunk)
                    digest.update(chunk)
        except (FileNotFoundError, NotADirectoryError):
            return VerifyResult(VerifyOutcome.MISSING)
        if actual != size:
            return VerifyResult(VerifyOutcome.SIZE_MISMATCH, actual)
        if digest.hexdigest() != sha256:
            return VerifyResult(VerifyOutcome.HASH_MISMATCH, actual)
        return VerifyResult(VerifyOutcome.OK, actual)

    def unreferenced_blobs(self, project_id: UUID, referenced_keys: set[str]) -> list[Path]:
        """Scoped listing for an explicit cleanup job; this module never deletes originals."""
        base = self.root / "projects" / str(project_id) / "blobs"
        if not base.is_dir():
            return []
        found = []
        for path in sorted(base.glob("*/*")):
            key = path.relative_to(self.root).as_posix()
            if _KEY.fullmatch(key) and key not in referenced_keys:
                found.append(path)
        return found


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
