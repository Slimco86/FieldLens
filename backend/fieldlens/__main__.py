"""``uv run python -m fieldlens`` — serve the API on the configured loopback address."""

import uvicorn

from fieldlens.config import get_settings


def main() -> None:
    settings = get_settings()  # validates loopback-only binding before the server starts
    uvicorn.run(
        "fieldlens.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level="info",
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
