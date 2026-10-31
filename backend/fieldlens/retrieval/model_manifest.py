"""Pinned local embedding model: repository revision and per-file SHA-256.

The model is a one-off, explicit setup download (``scripts/fetch_embedding_model.py``); the
application and the default tests never download anything. ``verify_model_dir`` is run before the
ONNX session is created, so a corrupted or substituted file refuses to load."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fieldlens.localenv import REPO_ROOT

MODEL_ID = "BAAI/bge-small-en-v1.5"
SOURCE_REPO = "Qdrant/bge-small-en-v1.5-onnx-Q"
SOURCE_REVISION = "aa8f8b060edb00e03bfdd08813a2949946c8ba55"
LICENSE = "MIT (BAAI/bge-small-en-v1.5; Qdrant ONNX int8 port; FastEmbed Apache-2.0)"
DIMENSION = 384
MAX_TOKENS = 512
ONNX_FILE = "model_optimized.onnx"
FILES: dict[str, str] = {
    "model_optimized.onnx": "51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431",
    "config.json": "13582bcf2effc85b7bf3d3f5532e686bc1c9ce86bb009d10f0ec33cbe92299dd",
    "ort_config.json": "99881c45e073696289224931dd48694398bc6bcd1fe7cb7018bca1e0cc00e1fc",
    "special_tokens_map.json": "5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a",
    "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    "tokenizer_config.json": "0b29c7bfc889e53b36d9dd3e686dd4300f6525110eaa98c76a5dafceb2029f53",
    "vocab.txt": "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3",
}
DEFAULT_DIR = (
    REPO_ROOT / ".local/fieldlens/models" / f"bge-small-en-v1.5-onnx-q-{SOURCE_REVISION[:8]}"
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def verify_model_dir(directory: Path) -> str | None:
    """None when every pinned file exists with the pinned hash, else a short reason."""
    for name, expected in FILES.items():
        path = directory / name
        if not path.is_file():
            return f"missing model file {name}"
        if sha256_of(path) != expected:
            return f"hash mismatch for {name}"
    return None
