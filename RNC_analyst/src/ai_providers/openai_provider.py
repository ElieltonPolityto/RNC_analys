from __future__ import annotations

import time
from typing import Any

from .utils import normalize_provider_payload, parse_json_payload
from ..prompts import RNC_REVIEW_SCHEMA, SYSTEM_INSTRUCTIONS


MAX_API_ATTEMPTS = 3
TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504, 520, 522, 524}


def analyze_pdf(
    *,
    api_key: str,
    model: str,
    pdf_bytes: bytes,
    file_name: str,
    prompt: str,
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    last_error: Exception | None = None
    for attempt in range(1, MAX_API_ATTEMPTS + 1):
        try:
            return _analyze_pdf_once(
                client=client,
                model=model,
                pdf_bytes=pdf_bytes,
                file_name=file_name,
                prompt=prompt,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_API_ATTEMPTS or not is_transient_provider_error(exc):
                raise
            time.sleep(attempt)

    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenAI API nao retornou resposta.")


def _analyze_pdf_once(
    *,
    client: Any,
    model: str,
    pdf_bytes: bytes,
    file_name: str,
    prompt: str,
) -> dict[str, Any]:
    uploaded = None

    try:
        uploaded = client.files.create(
            file=(file_name, pdf_bytes, "application/pdf"),
            purpose="user_data",
        )

        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": SYSTEM_INSTRUCTIONS}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_file", "file_id": uploaded.id},
                        {"type": "input_text", "text": prompt},
                    ],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "rnc_review",
                    "schema": RNC_REVIEW_SCHEMA,
                    "strict": True,
                }
            },
        )
        return normalize_provider_payload(parse_json_payload(response.output_text))
    finally:
        if uploaded is not None:
            try:
                client.files.delete(uploaded.id)
            except Exception:
                # Best-effort cleanup should not hide the provider response or original failure.
                pass


def is_transient_provider_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    try:
        if int(status_code) in TRANSIENT_STATUS_CODES:
            return True
    except (TypeError, ValueError):
        pass

    message = str(exc).lower()
    transient_tokens = [
        "520",
        "cloudflare",
        "temporarily unavailable",
        "timeout",
        "timed out",
        "connection error",
        "server error",
        "bad gateway",
        "service unavailable",
        "rate limit",
    ]
    return any(token in message for token in transient_tokens)

