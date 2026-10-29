"""Evidence-side storage of immutable originals (blobs outside database rows)."""

from .storage import BlobStore, VerifyOutcome, VerifyResult, blob_key

__all__ = ["BlobStore", "VerifyOutcome", "VerifyResult", "blob_key"]
