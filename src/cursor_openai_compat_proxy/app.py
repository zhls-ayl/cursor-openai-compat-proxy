from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.background import BackgroundTask

from cursor_openai_compat_proxy.config import Settings
from cursor_openai_compat_proxy.logging import configure_logging
from cursor_openai_compat_proxy.proxy import (
    build_response_headers,
    build_upstream_headers,
    build_upstream_url,
    is_json_content_type,
    parse_json_body,
    rewrite_target_path,
)


LOGGER = logging.getLogger("cursor_openai_compat_proxy")


def create_app(
    settings: Settings | None = None,
    http_client: httpx.AsyncClient | Any | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level)
        app.state.settings = settings

        if http_client is None:
            timeout = httpx.Timeout(settings.request_timeout_seconds, connect=10.0)
            app.state.http_client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
            should_close = True
        else:
            app.state.http_client = http_client
            should_close = False

        LOGGER.info(
            "Proxy started listen=%s:%s upstream=%s",
            settings.listen_host,
            settings.listen_port,
            settings.upstream_base_url,
        )
        try:
            yield
        finally:
            if should_close:
                await app.state.http_client.aclose()
            elif hasattr(app.state.http_client, "aclose"):
                await app.state.http_client.aclose()
            LOGGER.info("Proxy stopped")

    app = FastAPI(
        title="cursor-openai-compat-proxy",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/", response_class=PlainTextResponse)
    async def root() -> str:
        return "cursor-openai-compat-proxy is running"

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.api_route(
        "/v1/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def proxy(request: Request, path: str) -> Response:
        source_path = f"/v1/{path}"
        body = await request.body()
        payload = parse_json_body(body) if is_json_content_type(request.headers.get("content-type", "")) else None
        target_path, rewritten = rewrite_target_path(request.method, source_path, payload)

        if rewritten:
            LOGGER.info(
                "Rewriting method=%s source=%s target=%s",
                request.method,
                source_path,
                target_path,
            )

        upstream_url = build_upstream_url(settings.upstream_base_url, target_path, request.url.query)
        upstream_headers = build_upstream_headers(request.headers)
        client: httpx.AsyncClient = request.app.state.http_client

        try:
            if isinstance(payload, dict) and payload.get("stream") is True:
                upstream_request = client.build_request(
                    request.method,
                    upstream_url,
                    headers=upstream_headers,
                    content=body,
                )
                upstream_response = await client.send(upstream_request, stream=True)
                response_headers = build_response_headers(upstream_response.headers, rewritten, target_path)
                return StreamingResponse(
                    upstream_response.aiter_bytes(),
                    status_code=upstream_response.status_code,
                    headers=response_headers,
                    media_type=upstream_response.headers.get("content-type"),
                    background=BackgroundTask(upstream_response.aclose),
                )

            upstream_response = await client.request(
                request.method,
                upstream_url,
                headers=upstream_headers,
                content=body,
            )
            response_headers = build_response_headers(upstream_response.headers, rewritten, target_path)
            return Response(
                content=upstream_response.content,
                status_code=upstream_response.status_code,
                headers=response_headers,
                media_type=upstream_response.headers.get("content-type"),
            )
        except httpx.TimeoutException as exc:
            LOGGER.exception("Upstream timeout url=%s", upstream_url)
            raise HTTPException(status_code=504, detail="upstream request timed out") from exc
        except httpx.HTTPError as exc:
            LOGGER.exception("Upstream request failed url=%s", upstream_url)
            raise HTTPException(status_code=502, detail=f"upstream request failed: {exc.__class__.__name__}") from exc

    return app

