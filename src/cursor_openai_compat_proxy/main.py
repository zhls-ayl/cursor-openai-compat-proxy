from __future__ import annotations

import uvicorn

from cursor_openai_compat_proxy.app import create_app
from cursor_openai_compat_proxy.config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        create_app(settings),
        host=settings.listen_host,
        port=settings.listen_port,
        log_level=settings.log_level.lower(),
    )

