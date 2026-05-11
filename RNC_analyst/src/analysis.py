from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .ai_providers import openai_provider
from .pdf_tools import build_text_brief
from .prompts import build_review_prompt


SEVERITY_ORDER = {"baixa": 1, "media": 2, "alta": 3}
SEVERITY_ALIASES = {
    "baixa": "baixa",
    "baixo": "baixa",
    "low": "baixa",
    "media": "media",
    "média": "media",
    "medio": "media",
    "médio": "media",
    "medium": "media",
    "alta": "alta",
    "alto": "alta",
    "high": "alta",
}


def analyze_project(
    *,
    provider: str,
    api_key: str,
    model: str,
    pdf_bytes: bytes,
    file_name: str,
    pdf_summary: dict[str, Any],
    project_info: dict[str, str],
    base_instructions: str = "",
    similar_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    similar_cases = similar_cases or []
    text_brief = build_text_brief(pdf_summary)
    prompt = build_review_prompt(
        project_info,
        text_brief,
        base_instructions=base_instructions,
    )
    local_findings = build_local_findings(pdf_summary, project_info, similar_cases)

    if provider in {"Modelo local", "Pre-analise local"} or not api_key:
        provider_error = ""
        if provider == "OpenAI" and not api_key:
            provider_error = "OPENAI_API_KEY nao configurada no .env."
        return build_result(
            provider=provider,
            model=model,
            status="pre_analise_local",
            summary="Pre-analise local gerada.",
            overall_risk=estimate_overall_risk(local_findings),
            findings=local_findings,
            provider_error=provider_error,
            related_cases=similar_cases,
        )

    try:
        if provider == "OpenAI":
            payload = openai_provider.analyze_pdf(
                api_key=api_key,
                model=model,
                pdf_bytes=pdf_bytes,
                file_name=file_name,
                prompt=prompt,
            )
        else:
            raise ValueError(f"Provedor nao suportado: {provider}")

        ai_findings = [normalize_finding(item, "ia") for item in payload.get("findings", [])]
        merged = ai_findings + local_findings
        return build_result(
            provider=provider,
            model=model,
            status="concluido",
            summary=payload.get("summary", "Analise concluida."),
            overall_risk=payload.get("overall_risk") or estimate_overall_risk(merged),
            findings=merged,
            provider_error="",
            related_cases=similar_cases,
        )
    except Exception as exc:
        return build_result(
            provider=provider,
            model=model,
            status="erro_provedor",
            summary="A chamada de IA falhou. A pre-analise local foi mantida para nao interromper o fluxo.",
            overall_risk=estimate_overall_risk(local_findings),
            findings=local_findings,
            provider_error=humanize_provider_error(exc, provider, model),
            related_cases=similar_cases,
        )


def build_local_findings(
    pdf_summary: dict[str, Any],
    project_info: dict[str, str],
    similar_cases: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    similar_cases = similar_cases or []
    pages = pdf_summary.get("pages", [])
    critical_pages = pdf_summary.get("critical_pages", [])

    sparse_critical = [
        page
        for page in pages
        if page.get("is_critical") and page.get("is_text_sparse") and page.get("page", 0) >= 50
    ]
    if sparse_critical:
        page_list = ", ".join(str(page["page"]) for page in sparse_critical[:12])
        findings.append(
            make_finding(
                severity="media",
                category="Cotas/layout",
                page=sparse_critical[0]["page"],
                evidence=f"Paginas criticas com pouco texto extraivel: {page_list}.",
                recommendation="Priorizar revisao visual dessas paginas para cotas, etiquetas e posicionamento.",
                confidence=0.75,
            )
        )

    if critical_pages:
        page_list = ", ".join(str(page) for page in critical_pages[:20])
        findings.append(
            make_finding(
                severity="baixa",
                category="Escopo de revisao",
                page=None,
                evidence=f"Paginas classificadas como criticas para revisao: {page_list}.",
                recommendation="Usar estas paginas como fila de revisao tecnica antes da liberacao.",
                confidence=0.7,
            )
        )

    for warning in pdf_summary.get("warnings", []):
        findings.append(
            make_finding(
                severity="baixa",
                category="Qualidade do PDF",
                page=None,
                evidence=warning,
                recommendation="Normalizar ou reexportar o PDF caso a leitura fique incompleta.",
                confidence=0.8,
            )
        )

    return findings


def humanize_provider_error(exc: Exception, provider: str, model: str) -> str:
    raw = str(exc or "").strip()
    raw_lower = raw.lower()
    status_code = getattr(exc, "status_code", None) or extract_status_code(raw)

    if provider == "OpenAI":
        if status_code in {500, 502, 503, 504, 520, 522, 524} or "cloudflare" in raw_lower:
            code_text = f" {status_code}" if status_code else ""
            return (
                f"OpenAI API retornou erro temporario{code_text}. "
                "Tente executar a analise novamente em alguns minutos. "
                "A pre-analise local foi mantida."
            )
        if status_code == 429 or "rate limit" in raw_lower:
            return (
                "OpenAI API retornou limite de uso ou muitas chamadas em sequencia. "
                "Aguarde um pouco e tente novamente. A pre-analise local foi mantida."
            )
        if status_code in {401, 403} or "invalid api key" in raw_lower:
            return (
                "OpenAI API recusou a chave configurada. Confira OPENAI_API_KEY no arquivo .env. "
                "A pre-analise local foi mantida."
            )
        if status_code in {400, 404} and ("model" in raw_lower or "modelo" in raw_lower):
            return (
                f"OpenAI API nao aceitou o modelo configurado ({model}). "
                "Troque o modelo em Configuracoes ou no arquivo .env. "
                "A pre-analise local foi mantida."
            )

    if "<html" in raw_lower or len(raw) > 800:
        return (
            f"{provider} retornou uma resposta inesperada da API. "
            "Tente novamente; se persistir, confira chave, modelo e conexao. "
            "A pre-analise local foi mantida."
        )

    return limit_error_text(raw)


def extract_status_code(text: str) -> int | None:
    patterns = [
        r"error code[:\s]+(\d{3})",
        r"status code[:\s]+(\d{3})",
        r"\b(\d{3})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def limit_error_text(text: str, max_chars: int = 700) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def make_finding(
    *,
    severity: str,
    category: str,
    page: int | None,
    evidence: str,
    recommendation: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "severity": normalize_severity(severity),
        "category": category,
        "page": page,
        "evidence": evidence,
        "recommendation": recommendation,
        "confidence": coerce_confidence(confidence),
        "source": "triagem_local",
    }


def normalize_finding(item: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "severity": normalize_severity(item.get("severity")),
        "category": item.get("category") or "Sem categoria",
        "page": item.get("page"),
        "evidence": item.get("evidence") or "",
        "recommendation": item.get("recommendation") or "",
        "confidence": coerce_confidence(item.get("confidence")),
        "source": source,
    }


def normalize_severity(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return SEVERITY_ALIASES.get(normalized, "media")


def coerce_confidence(value: Any, *, default: float = 0.5) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


def build_result(
    *,
    provider: str,
    model: str,
    status: str,
    summary: str,
    overall_risk: str,
    findings: list[dict[str, Any]],
    provider_error: str,
    related_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    related_cases = related_cases or []
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider,
        "model": model,
        "status": status,
        "summary": summary,
        "overall_risk": overall_risk,
        "findings": findings,
        "provider_error": provider_error,
        "related_cases": related_cases,
        "related_cases_count": len(related_cases),
        "findings_count": len(findings),
        "max_severity": max_severity(findings),
    }


def estimate_overall_risk(findings: list[dict[str, Any]]) -> str:
    severity = max_severity(findings)
    if severity == "alta":
        return "alto"
    if severity == "media":
        return "medio"
    return "baixo"


def max_severity(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "baixa"
    return max((normalize_severity(item.get("severity")) for item in findings), key=lambda x: SEVERITY_ORDER.get(x, 0))
