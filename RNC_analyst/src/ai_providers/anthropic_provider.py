from __future__ import annotations

import base64
from typing import Any

from .utils import normalize_provider_payload, parse_json_payload
from ..prompts import SYSTEM_INSTRUCTIONS


def analyze_pdf(
    *,
    api_key: str,
    model: str,
    pdf_bytes: bytes,
    file_name: str,
    prompt: str,
) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    encoded_pdf = base64.b64encode(pdf_bytes).decode("ascii")

    message = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_INSTRUCTIONS,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": encoded_pdf,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    text = "\n".join(getattr(block, "text", "") for block in message.content)
    return normalize_provider_payload(parse_json_payload(text))

