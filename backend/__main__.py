from __future__ import annotations

import logging

import uvicorn

from backend.app import create_app
from backend.settings import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, proxy_headers=True)


if __name__ == "__main__":
    main()
