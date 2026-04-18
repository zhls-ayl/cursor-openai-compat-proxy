from __future__ import annotations

import json
from typing import Any, Mapping

import httpx


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

RESPONSES_HINT_KEYS = {
    "input",
    "instructions",
    "max_output_tokens",
    "parallel_tool_calls",
    "previous_response_id",
    "reasoning",
    "store",
    "text",
    "tool_choice",
    "truncation",
}


def is_json_content_type(content_type: str) -> bool:
    return "application/json" in content_type.lower()


def parse_json_body(body: bytes) -> dict[str, Any] | None:
    if not body:
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def is_responses_style_payload(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if "messages" in payload:
        return False
    if "input" in payload:
        return True
    return any(key in payload for key in RESPONSES_HINT_KEYS)


def rewrite_target_path(method: str, target_path: str, payload: dict[str, Any] | None) -> tuple[str, bool]:
    should_rewrite = (
        method.upper() == "POST"
        and target_path == "/v1/chat/completions"
        and is_responses_style_payload(payload)
    )
    if should_rewrite:
        return "/v1/responses", True
    return target_path, False


def build_upstream_url(upstream_base_url: str, target_path: str, query: str) -> str:
    upstream_url = f"{upstream_base_url}{target_path.removeprefix('/v1')}"
    if query:
        upstream_url = f"{upstream_url}?{query}"
    return upstream_url


def build_upstream_headers(headers: Mapping[str, str]) -> dict[str, str]:
    upstream_headers: dict[str, str] = {}
    for key, value in headers.items():
        lower_key = key.lower()
        if lower_key in HOP_BY_HOP_HEADERS:
            continue
        if lower_key in {"host", "content-length"}:
            continue
        upstream_headers[key] = value
    return upstream_headers


def build_response_headers(headers: httpx.Headers, rewritten: bool, target_path: str) -> dict[str, str]:
    response_headers: dict[str, str] = {}
    for key, value in headers.items():
        lower_key = key.lower()
        if lower_key in HOP_BY_HOP_HEADERS:
            continue
        if lower_key in {"content-length", "content-encoding"}:
            continue
        response_headers[key] = value
    response_headers["x-cursor-compat-rewrite"] = "1" if rewritten else "0"
    response_headers["x-cursor-compat-upstream-path"] = target_path
    return response_headers

