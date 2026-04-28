from __future__ import annotations

from typing import Any

from .utils import normalize_provider_payload, parse_json_payload
from ..prompts import RNC_REVIEW_SCHEMA, SYSTEM_INSTRUCTIONS


def analyze_text(
    *,
    api_key: str,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    from groq import Groq

    client = Groq(api_key=api_key)
    schema_hint = (
        "Responda como JSON com este formato: "
        f"{RNC_REVIEW_SCHEMA}. Nao inclua Markdown."
    )
    completion = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": f"{schema_hint}\n\n{prompt}"},
        ],
    )
    text = completion.choices[0].message.content
    return normalize_provider_payload(parse_json_payload(text))

