"""Upload intake, inert inspection and source records (no extraction)."""

from .routes import build_ingestion_router

__all__ = ["build_ingestion_router"]
