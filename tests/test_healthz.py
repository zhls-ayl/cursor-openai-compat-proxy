from fastapi.testclient import TestClient

from cursor_openai_compat_proxy.app import create_app
from cursor_openai_compat_proxy.config import Settings


class StubAsyncClient:
    async def aclose(self) -> None:
        return None


def test_healthz_returns_ok() -> None:
    settings = Settings(
        listen_host="127.0.0.1",
        listen_port=4000,
        upstream_base_url="https://example.com/v1",
        request_timeout_seconds=30.0,
        log_level="INFO",
    )
    app = create_app(settings=settings, http_client=StubAsyncClient())

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

