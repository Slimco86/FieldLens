"""Upload intake, inert inspection and source records (no extraction)."""

from .content import build_document_content_router
from .routes import build_ingestion_router

__all__ = ["build_document_content_router", "build_ingestion_router"]
