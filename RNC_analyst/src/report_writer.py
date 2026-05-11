from __future__ import annotations

import json
import re
from html import escape
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base_name = safe_filename(original_file_name).removesuffix(".pdf")
    xlsx_path = reports_dir / f"{timestamp}_{base_name}_relatorio_rnc.xlsx"
    md_path = reports_dir / f"{timestamp}_{base_name}_relatorio_rnc.md"
    pdf_path = reports_dir / f"{timestamp}_{base_name}_relatorio_rnc.pdf"

    write_excel(xlsx_path, project_info, result, pdf_summary)
    write_markdown(md_path, project_info, result, pdf_summary)
    write_pdf(pdf_path, project_info, result, pdf_summary)
    return {"xlsx": xlsx_path, "md": md_path, "pdf": pdf_path}


def write_pdf(
    path: Path,
    project_info: dict[str, str],
    result: dict[str, Any],
    pdf_summary: dict[str, Any],
) -> None:
    styles = build_pdf_styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.2 * cm,
        title="Relatorio Preventivo de RNC",
    )
    story: list[Any] = []

    story.append(Paragraph("Relatorio Preventivo de RNC", styles["Title"]))
    story.append(Paragraph("Revisao assistida antes do envio para producao", styles["Subtitle"]))
    story.append(Spacer(1, 0.35 * cm))

    inferred = pdf_summary.get("inferred", {})
    summary_data = [
        ["Arquivo", pdf_summary.get("file_name", "")],
        ["Cliente", first_report_value(project_info.get("cliente"), inferred.get("cliente"))],
        ["Documento", first_report_value(project_info.get("documento"), inferred.get("documento"))],
    ]
    story.append(Paragraph("Projeto analisado", styles["Heading"]))
    story.append(make_pdf_table(summary_data, styles, column_widths=[4.2 * cm, 12.0 * cm]))
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph("Resumo da analise", styles["Heading"]))
    story.append(Paragraph(pdf_text(compact_summary(result.get("summary", ""))), styles["Body"]))
    story.append(Spacer(1, 0.25 * cm))

    if result.get("provider_error"):
        story.append(Paragraph("Aviso", styles["Heading"]))
        story.append(Paragraph(pdf_text(result.get("provider_error")), styles["Warning"]))
        story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("Apontamentos para revisao", styles["Heading"]))
    findings = select_pdf_findings(result.get("findings", []))
    if not findings:
        story.append(Paragraph("Nenhum apontamento registrado.", styles["Body"]))
    for index, finding in enumerate(findings, start=1):
        page = finding.get("page")
        title = f"{index}. {finding.get('category', 'Sem categoria')}"
        story.append(Paragraph(pdf_text(title), styles["FindingTitle"]))
        finding_rows = [
            ["Pagina", page if page is not None else "nao informada"],
            ["Verificacao", limit_text(finding.get("evidence", ""), 520)],
            ["Acao", limit_text(finding.get("recommendation", ""), 520)],
        ]
        story.append(make_pdf_table(finding_rows, styles, column_widths=[3.0 * cm, 13.2 * cm]))
        story.append(Spacer(1, 0.22 * cm))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Orientacao para producao", styles["Heading"]))
    story.append(Paragraph(pdf_text(build_production_guidance(result, pdf_summary)), styles["Body"]))

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)


def first_report_value(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return "nao identificado"


def format_report_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "nao identificado"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    return parsed.strftime("%d/%m/%Y %H:%M")


def compact_summary(value: Any, max_chars: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return "Analise concluida. Revise os apontamentos abaixo antes da liberacao para producao."
    return limit_text(text, max_chars)


PDF_FINDINGS_LIMIT = 20


def select_pdf_findings(findings: list[dict[str, Any]], limit: int = PDF_FINDINGS_LIMIT) -> list[dict[str, Any]]:
    severity_order = {"alta": 0, "media": 1, "baixa": 2}
    sorted_findings = sorted(
        findings or [],
        key=lambda item: (
            severity_order.get(str(item.get("severity") or "").lower(), 1),
            item.get("page") is None,
            item.get("page") or 9999,
        ),
    )
    return sorted_findings[:limit]


def build_production_guidance(result: dict[str, Any], pdf_summary: dict[str, Any]) -> str:
    findings = result.get("findings", [])
    max_severity = str(result.get("max_severity") or "").lower()
    warnings = pdf_summary.get("warnings") or []
    if not findings:
        return (
            "Nao foram encontrados apontamentos automaticos relevantes. Ainda assim, mantenha a conferencia "
            "tecnica padrao do projeto antes do envio para producao."
        )
    if max_severity == "alta":
        return (
            "Antes de liberar o projeto para producao, trate os apontamentos destacados e registre as correcoes "
            "ou justificativas tecnicas aplicaveis. A liberacao deve ocorrer somente depois da conferencia dos "
            "itens indicados neste relatorio."
        )
    if warnings:
        return (
            "O projeto pode seguir para a etapa de revisao final, mas as verificacoes acima e os avisos de leitura "
            "do PDF devem ser conferidos antes da liberacao para producao."
        )
    return (
        "O projeto pode seguir para a etapa de revisao final apos a conferencia dos apontamentos listados. "
        "Corrija ou justifique os itens aplicaveis antes do envio para producao."
    )


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
        {"campo": "casos_historicos_relacionados", "valor": result.get("related_cases_count", 0)},
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
        pd.DataFrame(flatten_related_cases(result.get("related_cases", []))).to_excel(
            writer, sheet_name="Casos Historicos", index=False
        )
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
        f"- Casos historicos relacionados: {result.get('related_cases_count', 0)}",
        "",
        "## Resumo",
        "",
        result.get("summary", ""),
        "",
    ]

    related_cases = result.get("related_cases", [])
    if related_cases:
        lines.extend(["## Casos historicos relacionados", ""])
        for case in related_cases:
            lines.extend(
                [
                    f"### {case.get('case_id', '')}",
                    "",
                    f"- Busca: {case.get('retrieval_method', '')}",
                    f"- Similaridade: {case.get('similarity', '')}",
                    f"- Score: {case.get('score', '')}",
                    f"- Score vetorial: {case.get('vector_score', '')}",
                    f"- Tipo de RNC: {case.get('rnc_type', '')}",
                    f"- Severidade historica: {case.get('severity', '')}",
                    f"- Causa raiz: {case.get('root_cause', '')}",
                    f"- Acao preventiva: {case.get('preventive_action', '')}",
                    "",
                ]
            )

    lines.extend(["## Apontamentos", ""])
    findings = result.get("findings", [])
    if not findings:
        lines.extend(["Nenhum apontamento registrado.", ""])

    for index, finding in enumerate(findings, start=1):
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


def flatten_related_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not cases:
        return [
            {
                "case_id": "",
                "retrieval_method": "",
                "similarity": "",
                "score": "",
                "vector_score": "",
                "rnc_type": "",
                "severity": "",
                "root_cause": "",
                "preventive_action": "",
            }
        ]
    return [
        {
            "case_id": case.get("case_id", ""),
            "retrieval_method": case.get("retrieval_method", ""),
            "similarity": case.get("similarity", ""),
            "score": case.get("score", ""),
            "vector_score": case.get("vector_score", ""),
            "title": case.get("title", ""),
            "customer": case.get("customer", ""),
            "document": case.get("document", ""),
            "project": case.get("project", ""),
            "revision": case.get("revision", ""),
            "rnc_type": case.get("rnc_type", ""),
            "severity": case.get("severity", ""),
            "root_cause": case.get("root_cause", ""),
            "corrective_action": case.get("corrective_action", ""),
            "preventive_action": case.get("preventive_action", ""),
            "keywords": ", ".join(case.get("keywords") or []),
        }
        for case in cases
    ]


def build_pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "Title": ParagraphStyle(
            "RncTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=6,
        ),
        "Subtitle": ParagraphStyle(
            "RncSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#4b5563"),
        ),
        "Heading": ParagraphStyle(
            "RncHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#111827"),
            spaceBefore=4,
            spaceAfter=6,
        ),
        "Body": ParagraphStyle(
            "RncBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1f2937"),
        ),
        "Warning": ParagraphStyle(
            "RncWarning",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#92400e"),
        ),
        "Cell": ParagraphStyle(
            "RncCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1f2937"),
        ),
        "CellBold": ParagraphStyle(
            "RncCellBold",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#111827"),
        ),
        "FindingTitle": ParagraphStyle(
            "RncFindingTitle",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#111827"),
            spaceAfter=4,
        ),
    }


def make_pdf_table(
    rows: list[list[Any]],
    styles: dict[str, ParagraphStyle],
    *,
    column_widths: list[float],
    has_header: bool = False,
) -> Table:
    table_rows = []
    for row_index, row in enumerate(rows):
        table_row = []
        for cell_index, cell in enumerate(row):
            style = styles["CellBold"] if cell_index == 0 or (has_header and row_index == 0) else styles["Cell"]
            table_row.append(Paragraph(pdf_text(cell), style))
        table_rows.append(table_row)

    table = Table(table_rows, colWidths=column_widths, repeatRows=1 if has_header else 0)
    style_commands = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if has_header:
        style_commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ]
        )
    else:
        style_commands.append(("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")))
    table.setStyle(TableStyle(style_commands))
    return table


def pdf_text(value: Any) -> str:
    text = str(value if value is not None else "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return escape(text).replace("\n", "<br/>")


def limit_text(value: Any, max_chars: int) -> str:
    text = str(value if value is not None else "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def draw_footer(canvas: Any, doc: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(1.4 * cm, 0.65 * cm, "RNC Analyst - revisao preventiva")
    canvas.drawRightString(19.6 * cm, 0.65 * cm, f"Pagina {doc.page}")
    canvas.restoreState()
