import httpx
from fastapi.testclient import TestClient

from cursor_openai_compat_proxy.app import create_app
from cursor_openai_compat_proxy.config import Settings


class StubAsyncClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def request(self, method: str, url: str, headers=None, content=None):
        self.calls.append(
            {
                "kind": "request",
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "content": content,
            }
        )
        return self.response

    def build_request(self, method: str, url: str, headers=None, content=None):
        return {
            "method": method,
            "url": url,
            "headers": dict(headers or {}),
            "content": content,
        }

    async def send(self, request, stream: bool = False):
        self.calls.append(
            {
                "kind": "send",
                "method": request["method"],
                "url": request["url"],
                "headers": request["headers"],
                "content": request["content"],
                "stream": stream,
            }
        )
        return self.response

    async def aclose(self) -> None:
        return None


def make_settings() -> Settings:
    return Settings(
        listen_host="127.0.0.1",
        listen_port=4000,
        upstream_base_url="https://example.com/v1",
        request_timeout_seconds=30.0,
        log_level="INFO",
    )


def get_header_value(headers: dict[str, object], name: str) -> object | None:
    lowered_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered_name:
            return value
    return None


def test_rewrites_responses_style_payload_and_preserves_authorization() -> None:
    stub_client = StubAsyncClient(
        httpx.Response(
            200,
            json={"id": "resp_123", "object": "response"},
            headers={"content-type": "application/json"},
        )
    )
    app = create_app(settings=make_settings(), http_client=stub_client)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer upstream-key"},
            json={"model": "gpt-5.4", "input": "hello", "stream": False},
        )

    assert response.status_code == 200
    assert response.headers["x-cursor-compat-rewrite"] == "1"
    assert response.headers["x-cursor-compat-upstream-path"] == "/v1/responses"
    assert stub_client.calls[0]["url"] == "https://example.com/v1/responses"
    assert get_header_value(stub_client.calls[0]["headers"], "Authorization") == "Bearer upstream-key"


def test_standard_chat_payload_keeps_chat_completions_path() -> None:
    stub_client = StubAsyncClient(
        httpx.Response(
            200,
            json={"id": "chatcmpl_123", "object": "chat.completion"},
            headers={"content-type": "application/json"},
        )
    )
    app = create_app(settings=make_settings(), http_client=stub_client)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer upstream-key"},
            json={
                "model": "gpt-5.4",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
        )

    assert response.status_code == 200
    assert response.headers["x-cursor-compat-rewrite"] == "0"
    assert response.headers["x-cursor-compat-upstream-path"] == "/v1/chat/completions"
    assert stub_client.calls[0]["url"] == "https://example.com/v1/chat/completions"


def test_streaming_requests_use_stream_path() -> None:
    stub_client = StubAsyncClient(
        httpx.Response(
            200,
            content=b"data: hello\n\n",
            headers={"content-type": "text/event-stream"},
        )
    )
    app = create_app(settings=make_settings(), http_client=stub_client)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer upstream-key"},
            json={"model": "gpt-5.4", "input": "hello", "stream": True},
        )

    assert response.status_code == 200
    assert response.headers["x-cursor-compat-rewrite"] == "1"
    assert stub_client.calls[0]["kind"] == "send"
    assert stub_client.calls[0]["stream"] is True
    assert stub_client.calls[0]["url"] == "https://example.com/v1/responses"
