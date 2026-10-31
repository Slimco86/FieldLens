"""Local embedder boundary: one interface, a real FastEmbed backend and an offline fake.

Meta exposes no embeddings endpoint for our key (MI-6 probe: 404), so embeddings are local and
CPU-only. The application never downloads a model: a missing or hash-mismatched model file makes
the embedder *unavailable*, retrieval then reports an explicit degraded state (exact + full text
only) and nothing pretends to be hybrid. Every vector is tied to an ``EmbeddingSpec`` whose
SHA-256 fingerprint covers model id/revision, dimension, quantization, normalization, prefixes,
preprocessing and library version, so changing any of them builds a new index."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from fieldlens.config import Settings

from . import model_manifest as mm
from .text import preprocess, search_text

logger = logging.getLogger(__name__)
BATCH_SIZE = 16
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
PREPROCESSING_VERSION = "nfkc-ws-v1"
ACQUIRE_TIMEOUT_S = 5.0
RETRY_AFTER_FAILURE_S = 30.0


@dataclass(frozen=True)
class EmbeddingSpec:
    provider: str
    model_id: str
    model_revision: str
    dimension: int
    quantization: str
    normalization: str
    document_prefix: str
    query_prefix: str
    max_tokens: int
    preprocessing: str
    library: str

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def public(self) -> dict[str, Any]:
        return {**asdict(self), "fingerprint": self.fingerprint}


class EmbedderUnavailable(Exception):
    """No usable embedder (disabled, model missing/corrupt, library error). ``code`` is stable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Embedder(Protocol):
    spec: EmbeddingSpec

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _l2(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [float(v) / norm for v in vector] if norm > 0 else [float(v) for v in vector]


class FakeHashEmbedder:
    """Deterministic offline embedder (feature hashing of words). Default tests only: it carries
    no semantics beyond word overlap, so synthetic results never speak for the real model."""

    def __init__(self, dimension: int = 384, *, name: str = "fake-hash") -> None:
        self.spec = EmbeddingSpec(
            provider="fake",
            model_id=name,
            model_revision="1",
            dimension=dimension,
            quantization="none",
            normalization="l2",
            document_prefix="",
            query_prefix="",
            max_tokens=100000,
            preprocessing=PREPROCESSING_VERSION,
            library="builtin",
        )
        self.calls = 0

    def _vec(self, text: str) -> list[float]:
        vector = [0.0] * self.spec.dimension
        words = search_text(preprocess(text)).split()
        for word in words:
            digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.spec.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _l2(vector)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return self._vec(text)


class FastEmbedEmbedder:
    """BAAI/bge-small-en-v1.5 (Qdrant int8 ONNX port) via FastEmbed, CPU only, 2 threads."""

    def __init__(self, model_dir: Path) -> None:
        reason = mm.verify_model_dir(model_dir)
        if reason is not None:
            raise EmbedderUnavailable(
                "model_missing", f"{reason}; run scripts/fetch_embedding_model.py"
            )
        try:
            import fastembed
            from fastembed import TextEmbedding

            self._model = TextEmbedding(
                model_name=mm.MODEL_ID,
                specific_model_path=str(model_dir),
                local_files_only=True,
                threads=2,
                providers=["CPUExecutionProvider"],
            )
            version = getattr(fastembed, "__version__", "unknown")
        except Exception as exc:  # library/ONNX failure is an unavailable embedder, not a crash
            raise EmbedderUnavailable("model_load_failed", type(exc).__name__) from exc
        self.spec = EmbeddingSpec(
            provider="fastembed",
            model_id=mm.MODEL_ID,
            model_revision=f"{mm.SOURCE_REPO}@{mm.SOURCE_REVISION}",
            dimension=mm.DIMENSION,
            quantization="int8-onnx",
            normalization="l2",
            document_prefix="",
            query_prefix=QUERY_PREFIX,
            max_tokens=mm.MAX_TOKENS,
            preprocessing=PREPROCESSING_VERSION,
            library=f"fastembed=={version}",
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [_l2(v.tolist()) for v in self._model.embed(texts, batch_size=BATCH_SIZE)]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        prefix = self.spec.document_prefix
        return self._embed([prefix + preprocess(t) for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.spec.query_prefix + preprocess(text)])[0]


@dataclass(frozen=True)
class EmbedderStatus:
    state: str  # ready | unavailable | disabled
    code: str | None = None
    message: str | None = None
    spec: EmbeddingSpec | None = None


class EmbedderProvider:
    """Lazily creates the configured embedder once, serializes CPU use (one embedding at a time)
    and remembers a load failure briefly instead of re-reading a missing model per request."""

    def __init__(self, settings: Settings, *, embedder: Embedder | None = None) -> None:
        self._settings = settings
        self._embedder: Embedder | None = embedder
        self._failure: tuple[float, EmbedderUnavailable] | None = None
        self._load_lock = threading.Lock()
        self._use_lock = threading.Lock()

    def _create(self) -> Embedder:
        kind = self._settings.embedding_provider
        if kind == "none":
            raise EmbedderUnavailable(
                "embedder_disabled", "embeddings are disabled by configuration"
            )
        if kind == "fake":
            return FakeHashEmbedder()
        return FastEmbedEmbedder(self._settings.embedding_model_dir or mm.DEFAULT_DIR)

    def get(self) -> Embedder:
        if self._embedder is not None:
            return self._embedder
        with self._load_lock:
            if self._embedder is not None:
                return self._embedder
            if self._failure and time.monotonic() - self._failure[0] < RETRY_AFTER_FAILURE_S:
                raise self._failure[1]
            try:
                self._embedder = self._create()
            except EmbedderUnavailable as exc:
                self._failure = (time.monotonic(), exc)
                logger.warning("embedder unavailable: %s", exc.code)
                raise
            self._failure = None
            return self._embedder

    def status(self) -> EmbedderStatus:
        try:
            return EmbedderStatus("ready", spec=self.get().spec)
        except EmbedderUnavailable as exc:
            state = "disabled" if exc.code == "embedder_disabled" else "unavailable"
            return EmbedderStatus(state, exc.code, exc.message)

    def _guarded(self, fn: Any, timeout: float) -> Any:
        if not self._use_lock.acquire(timeout=timeout):
            raise EmbedderUnavailable("embedder_busy", "embedder is busy with another request")
        try:
            return fn()
        except EmbedderUnavailable:
            raise
        except Exception as exc:
            raise EmbedderUnavailable("embedding_failed", type(exc).__name__) from exc
        finally:
            self._use_lock.release()

    def embed_documents(self, texts: Sequence[str], timeout: float = 60.0) -> list[list[float]]:
        embedder = self.get()
        out: list[list[float]] = self._guarded(lambda: embedder.embed_documents(texts), timeout)
        return out

    def embed_query(self, text: str, timeout: float = ACQUIRE_TIMEOUT_S) -> list[float]:
        embedder = self.get()
        out: list[float] = self._guarded(lambda: embedder.embed_query(text), timeout)
        return out
