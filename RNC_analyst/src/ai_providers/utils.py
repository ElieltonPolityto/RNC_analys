from __future__ import annotations

import json
import re
from typing import Any


def parse_json_payload(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if not value:
        raise ValueError("Resposta vazia do provedor de IA.")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload.get("findings") or []
    if not isinstance(findings, list):
        findings = []
    return {
        "summary": str(payload.get("summary") or "Analise concluida."),
        "overall_risk": payload.get("overall_risk") or "medio",
        "findings": findings,
    }

