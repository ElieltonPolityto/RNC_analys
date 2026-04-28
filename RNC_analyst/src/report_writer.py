from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .pdf_tools import safe_filename


def write_reports(
    *,
    reports_dir: Path,
    project_info: dict[str, str],
    result: dict[str, Any],
    pdf_summary: dict[str, Any],
    original_file_name: str,
) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = safe_filename(original_file_name).removesuffix(".pdf")
    xlsx_path = reports_dir / f"{timestamp}_{base_name}_relatorio_rnc.xlsx"
    md_path = reports_dir / f"{timestamp}_{base_name}_relatorio_rnc.md"

    write_excel(xlsx_path, project_info, result, pdf_summary)
    write_markdown(md_path, project_info, result, pdf_summary)
    return {"xlsx": xlsx_path, "md": md_path}


def write_excel(
    path: Path,
    project_info: dict[str, str],
    result: dict[str, Any],
    pdf_summary: dict[str, Any],
) -> None:
    summary_rows = [
        {"campo": "gerado_em", "valor": result.get("generated_at", "")},
        {"campo": "usuario", "valor": project_info.get("usuario", "")},
        {"campo": "cliente", "valor": project_info.get("cliente", "")},
        {"campo": "documento", "valor": project_info.get("documento", "")},
        {"campo": "pedido", "valor": project_info.get("pedido", "")},
        {"campo": "projeto", "valor": project_info.get("projeto", "")},
        {"campo": "revisao", "valor": project_info.get("revisao", "")},
        {"campo": "provedor", "valor": result.get("provider", "")},
        {"campo": "modelo", "valor": result.get("model", "")},
        {"campo": "status", "valor": result.get("status", "")},
        {"campo": "risco_geral", "valor": result.get("overall_risk", "")},
        {"campo": "qtd_apontamentos", "valor": result.get("findings_count", 0)},
        {"campo": "severidade_maxima", "valor": result.get("max_severity", "")},
        {"campo": "resumo", "valor": result.get("summary", "")},
        {"campo": "erro_provedor", "valor": result.get("provider_error", "")},
    ]

    findings = result.get("findings", [])
    if not findings:
        findings = [
            {
                "severity": "baixa",
                "category": "Sem apontamentos",
                "page": None,
                "evidence": "Nenhum apontamento registrado.",
                "recommendation": "",
                "confidence": 0,
                "source": "",
            }
        ]

    pages = pdf_summary.get("pages", [])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Resumo", index=False)
        pd.DataFrame(findings).to_excel(writer, sheet_name="Apontamentos", index=False)
        pd.DataFrame(pages).to_excel(writer, sheet_name="Paginas", index=False)

        for sheet in writer.book.worksheets:
            for column_cells in sheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in column_cells)
                sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 12), 80)


def write_markdown(
    path: Path,
    project_info: dict[str, str],
    result: dict[str, Any],
    pdf_summary: dict[str, Any],
) -> None:
    lines = [
        "# Relatorio Preventivo de RNC",
        "",
        f"- Gerado em: {result.get('generated_at', '')}",
        f"- Usuario: {project_info.get('usuario', '')}",
        f"- Cliente: {project_info.get('cliente', '')}",
        f"- Documento: {project_info.get('documento', '')}",
        f"- Pedido: {project_info.get('pedido', '')}",
        f"- Projeto: {project_info.get('projeto', '')}",
        f"- Revisao: {project_info.get('revisao', '')}",
        f"- Provedor: {result.get('provider', '')}",
        f"- Modelo: {result.get('model', '')}",
        f"- Status: {result.get('status', '')}",
        f"- Risco geral: {result.get('overall_risk', '')}",
        "",
        "## Resumo",
        "",
        result.get("summary", ""),
        "",
        "## Apontamentos",
        "",
    ]

    for index, finding in enumerate(result.get("findings", []), start=1):
        page = finding.get("page")
        lines.extend(
            [
                f"### {index}. {finding.get('category', 'Sem categoria')}",
                "",
                f"- Severidade: {finding.get('severity', '')}",
                f"- Pagina: {page if page is not None else 'nao informada'}",
                f"- Confianca: {finding.get('confidence', '')}",
                f"- Fonte: {finding.get('source', '')}",
                f"- Evidencia: {finding.get('evidence', '')}",
                f"- Recomendacao: {finding.get('recommendation', '')}",
                "",
            ]
        )

    if result.get("provider_error"):
        lines.extend(["## Erro do provedor", "", result["provider_error"], ""])

    lines.extend(
        [
            "## Dados tecnicos do PDF",
            "",
            "```json",
            json.dumps(
                {
                    "pages_count": pdf_summary.get("pages_count"),
                    "inferred": pdf_summary.get("inferred"),
                    "critical_pages": pdf_summary.get("critical_pages"),
                    "warnings": pdf_summary.get("warnings"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")

