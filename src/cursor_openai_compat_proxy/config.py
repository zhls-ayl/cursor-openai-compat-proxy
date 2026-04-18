from __future__ import annotations

import os
from dataclasses import dataclass


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    listen_host: str
    listen_port: int
    upstream_base_url: str
    request_timeout_seconds: float
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        upstream_base_url = _get_env("UPSTREAM_BASE_URL")
        if not upstream_base_url:
            raise RuntimeError("UPSTREAM_BASE_URL is required")

        upstream_base_url = upstream_base_url.rstrip("/")
        if not upstream_base_url.endswith("/v1"):
            raise RuntimeError("UPSTREAM_BASE_URL must end with /v1")

        return cls(
            listen_host=_get_env("LISTEN_HOST", "127.0.0.1"),
            listen_port=int(_get_env("LISTEN_PORT", "4000")),
            upstream_base_url=upstream_base_url,
            request_timeout_seconds=float(_get_env("REQUEST_TIMEOUT_SECONDS", "600")),
            log_level=_get_env("LOG_LEVEL", "INFO").upper(),
        )

