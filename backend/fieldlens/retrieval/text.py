"""Token estimation and search-text normalization shared by the chunker and the query side."""

from __future__ import annotations

import re
import unicodedata

_TOKEN = re.compile(r"[^\W\d_]+|\d+|[^\s\w]|_")
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)
_SPACES = re.compile(r"\s+")


def estimate_tokens(text: str) -> int:
    """Model-agnostic estimate calibrated to WordPiece: a letter run costs ceil(len/4), a digit
    run ceil(len/2) and every symbol 1. Measured against the bge-small tokenizer on the
    approved Volve subset this is within about -15%/+9% (mean 1.00); it is a budget, not a
    tokenizer, so the opt-in embedder test re-checks the 512-token window on real chunks."""
    total = 0
    for token in _TOKEN.findall(text):
        head = token[0]
        if head.isdigit():
            total += max(1, -(-len(token) // 2))
        elif head.isalpha():
            total += max(1, -(-len(token) // 4))
        else:
            total += 1
    return total


def preprocess(text: str) -> str:
    """Embedding preprocessing (part of the embedding fingerprint): NFKC + whitespace collapse."""
    return _SPACES.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def search_text(text: str) -> str:
    """Lowercased alphanumeric words joined by spaces; the same function feeds the stored
    ``tsv`` column and every query, so punctuation never makes the two sides disagree."""
    return _SPACES.sub(
        " ", _NON_ALNUM.sub(" ", unicodedata.normalize("NFKC", text).lower())
    ).strip()


def norm_identifier(value: str) -> str:
    """Identifier normalization for exact lookup: lowercase, trimmed, single spaces. Punctuation
    (``/``, ``-``, ``.``) is preserved because it is part of the identifier."""
    return _SPACES.sub(" ", unicodedata.normalize("NFKC", value)).strip().lower()
