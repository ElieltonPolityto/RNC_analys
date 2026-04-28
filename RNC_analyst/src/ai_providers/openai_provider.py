from __future__ import annotations

from io import BytesIO
from typing import Any

from .utils import normalize_provider_payload, parse_json_payload
from ..prompts import RNC_REVIEW_SCHEMA, SYSTEM_INSTRUCTIONS


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
    pdf_file = BytesIO(pdf_bytes)
    pdf_file.name = file_name
    uploaded = client.files.create(file=pdf_file, purpose="vision")

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

