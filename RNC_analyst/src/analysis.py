from __future__ import annotations

from datetime import datetime
from typing import Any

from .ai_providers import openai_provider
from .case_base import build_cases_prompt_context
from .pdf_tools import build_text_brief
from .prompts import build_review_prompt


SEVERITY_ORDER = {"baixa": 1, "media": 2, "alta": 3}


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
    similar_cases_context = build_cases_prompt_context(similar_cases)
    prompt = build_review_prompt(
        project_info,
        text_brief,
        base_instructions=base_instructions,
        similar_cases_context=similar_cases_context,
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
            provider_error=str(exc),
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
    inferred = pdf_summary.get("inferred", {})

    if not (project_info.get("cliente") or inferred.get("cliente")):
        findings.append(
            make_finding(
                severity="media",
                category="Cadastro/documentacao",
                page=1,
                evidence="Cliente nao identificado automaticamente no PDF.",
                recommendation="Confirmar se o campo de cliente esta preenchido e legivel no projeto.",
                confidence=0.55,
            )
        )

    if not (project_info.get("documento") or inferred.get("documento")):
        findings.append(
            make_finding(
                severity="media",
                category="Cadastro/documentacao",
                page=1,
                evidence="Documento do projeto nao identificado automaticamente.",
                recommendation="Confirmar numero de documento antes do envio para a fabrica.",
                confidence=0.55,
            )
        )

    if not project_info.get("revisao"):
        findings.append(
            make_finding(
                severity="baixa",
                category="Revisao",
                page=1,
                evidence="Revisao nao informada pelo usuario no cadastro da analise.",
                recommendation="Informar a revisao analisada para manter rastreabilidade.",
                confidence=0.8,
            )
        )

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
                evidence=f"Paginas classificadas como criticas para RNC: {page_list}.",
                recommendation="Usar estas paginas como fila de revisao tecnica antes da liberacao.",
                confidence=0.7,
            )
        )

    for case in similar_cases[:5]:
        severity = "media" if case.get("similarity") in {"alta", "media"} else "baixa"
        findings.append(
            make_finding(
                severity=severity,
                category="Historico RNC",
                page=None,
                evidence=(
                    f"Caso historico {case.get('case_id')} com similaridade {case.get('similarity')} "
                    f"(score {case.get('score')}). Tipo de RNC: {case.get('rnc_type') or 'nao informado'}."
                ),
                recommendation=(
                    "Comparar o projeto atual com esse caso antes da liberacao. "
                    f"Causa historica: {case.get('root_cause') or 'nao informada'}."
                ),
                confidence=float(case.get("score") or 0.4),
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
        "severity": severity,
        "category": category,
        "page": page,
        "evidence": evidence,
        "recommendation": recommendation,
        "confidence": confidence,
        "source": "triagem_local",
    }


def normalize_finding(item: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "severity": item.get("severity") or "media",
        "category": item.get("category") or "Sem categoria",
        "page": item.get("page"),
        "evidence": item.get("evidence") or "",
        "recommendation": item.get("recommendation") or "",
        "confidence": float(item.get("confidence") or 0.5),
        "source": source,
    }


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
    return max((item.get("severity", "baixa") for item in findings), key=lambda x: SEVERITY_ORDER.get(x, 0))
