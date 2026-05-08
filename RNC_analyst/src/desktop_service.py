from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - the launcher installs python-dotenv for normal use.
    def load_dotenv(*_: Any, **__: Any) -> bool:
        return False

from .analysis import analyze_project
from .case_base import (
    ensure_case_base,
    fingerprint_case_base,
    generate_metadata_files,
    index_all_cases,
    init_case_tables,
    list_case_dirs,
    list_indexed_cases,
    load_base_instructions,
    prompt_hash,
    save_base_instructions,
)
from .database import init_db, list_analyses, save_analysis
from .pdf_tools import build_text_brief, ensure_runtime_dirs, parse_pdf_bytes, save_uploaded_pdf
from .prompts import SYSTEM_INSTRUCTIONS, build_review_prompt
from .report_writer import write_reports
from .vector_store import load_vector_config


DEFAULT_OPENAI_MODEL = "gpt-5-mini"
MAX_UPLOAD_SIZE_MB = 80
MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
DEFAULT_CASE_LIMIT = 5
ProgressCallback = Callable[[int, str], None]


@dataclass(frozen=True)
class DesktopContext:
    base_dir: Path
    runtime_dirs: dict[str, Path]
    case_base_paths: dict[str, Path]
    db_path: Path


@dataclass(frozen=True)
class PdfLoadResult:
    path: Path
    bytes_data: bytes
    summary: dict[str, Any]


@dataclass(frozen=True)
class AnalysisResult:
    analysis_id: int
    result: dict[str, Any]
    report_paths: dict[str, Path]
    project_info: dict[str, str]
    pdf_summary: dict[str, Any]


def create_context(base_dir: Path) -> DesktopContext:
    load_dotenv(base_dir / ".env", override=True)
    runtime_dirs = ensure_runtime_dirs(base_dir)
    case_base_paths = ensure_case_base(base_dir)
    db_path = runtime_dirs["data"] / "rnc_analyst.db"
    init_db(db_path)
    init_case_tables(db_path)
    return DesktopContext(
        base_dir=base_dir,
        runtime_dirs=runtime_dirs,
        case_base_paths=case_base_paths,
        db_path=db_path,
    )


def openai_model() -> str:
    return normalize_model_id(os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL))


def save_openai_model(base_dir: Path, model: str) -> str:
    normalized = normalize_model_id(model)
    env_path = base_dir / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated = False
    for index, line in enumerate(lines):
        if line.strip().startswith("OPENAI_MODEL="):
            lines[index] = f"OPENAI_MODEL={normalized}"
            updated = True
            break
    if not updated:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"OPENAI_MODEL={normalized}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["OPENAI_MODEL"] = normalized
    return normalized


def ai_mode_label() -> str:
    model = openai_model()
    if model == DEFAULT_OPENAI_MODEL:
        return f"IA economica: {model}"
    return f"IA avancada: {model}"


def normalize_model_id(value: str) -> str:
    model = (value or "").strip()
    model = re.sub(r"[\s_]+", "-", model)
    return model or DEFAULT_OPENAI_MODEL


def load_pdf(path: Path) -> PdfLoadResult:
    if not path.exists():
        raise ValueError("Arquivo PDF nao encontrado.")
    if path.suffix.lower() != ".pdf":
        raise ValueError("Selecione um arquivo PDF valido.")
    file_bytes = path.read_bytes()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"O PDF tem mais de {MAX_UPLOAD_SIZE_MB} MB. Reduza ou divida o arquivo antes da analise.")
    summary = parse_pdf_bytes(file_bytes, path.name)
    return PdfLoadResult(path=path, bytes_data=file_bytes, summary=summary)


def build_effective_prompt(context: DesktopContext, loaded_pdf: PdfLoadResult) -> str:
    base_instructions = load_base_instructions(context.case_base_paths["instructions"])
    project_info = build_project_info(loaded_pdf.summary.get("inferred", {}))
    user_prompt = build_review_prompt(
        project_info,
        build_text_brief(loaded_pdf.summary),
        base_instructions=base_instructions,
    )
    return "\n\n".join(
        [
            "=== SYSTEM INSTRUCTIONS ===",
            SYSTEM_INSTRUCTIONS,
            "=== USER PROMPT ===",
            user_prompt,
        ]
    )


def run_analysis(
    context: DesktopContext,
    loaded_pdf: PdfLoadResult,
    progress: ProgressCallback | None = None,
) -> AnalysisResult:
    emit_progress(progress, 0, "Preparando analise")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    provider = "OpenAI" if api_key else "Modelo local"
    model = openai_model() if api_key else "local"
    inferred = loaded_pdf.summary.get("inferred", {})
    project_info = build_project_info(inferred)

    emit_progress(progress, 10, "Salvando PDF local")
    upload_path = save_uploaded_pdf(
        loaded_pdf.bytes_data,
        loaded_pdf.path.name,
        context.runtime_dirs["uploads"],
    )
    emit_progress(progress, 20, "Carregando instrucoes")
    base_instructions = load_base_instructions(context.case_base_paths["instructions"])
    emit_progress(progress, 35, "Preparando contexto")
    similar_cases: list[dict[str, Any]] = []
    emit_progress(progress, 50, "Executando analise com IA/local")
    result = analyze_project(
        provider=provider,
        api_key=api_key,
        model=model,
        pdf_bytes=loaded_pdf.bytes_data,
        file_name=loaded_pdf.path.name,
        pdf_summary=loaded_pdf.summary,
        project_info=project_info,
        base_instructions=base_instructions,
        similar_cases=similar_cases,
    )
    emit_progress(progress, 80, "Gerando relatorios")
    report_paths = write_reports(
        reports_dir=context.runtime_dirs["reports"],
        project_info=project_info,
        result=result,
        pdf_summary=loaded_pdf.summary,
        original_file_name=loaded_pdf.path.name,
    )
    emit_progress(progress, 90, "Salvando historico")
    record = build_record(
        project_info=project_info,
        result=result,
        pdf_summary=loaded_pdf.summary,
        pdf_name=loaded_pdf.path.name,
        upload_path=upload_path,
        report_paths=report_paths,
        related_cases=similar_cases,
        base_prompt=base_instructions,
        base_prompt_path=context.case_base_paths["instructions"],
    )
    analysis_id = save_analysis(context.db_path, record)
    emit_progress(progress, 100, "Analise concluida")
    return AnalysisResult(
        analysis_id=analysis_id,
        result=result,
        report_paths=report_paths,
        project_info=project_info,
        pdf_summary=loaded_pdf.summary,
    )


def emit_progress(progress: ProgressCallback | None, percent: int, message: str) -> None:
    if progress is not None:
        progress(max(0, min(100, percent)), message)


def build_project_info(inferred: dict[str, Any]) -> dict[str, str]:
    return {
        "usuario": os.getenv("USERNAME", "").strip() or os.getenv("USER", "").strip() or "Usuario local",
        "cliente": str(inferred.get("cliente") or "").strip(),
        "documento": str(inferred.get("documento") or "").strip(),
        "pedido": str(inferred.get("pedido") or "").strip(),
        "projeto": str(inferred.get("projeto") or "").strip(),
        "revisao": str(inferred.get("revisao") or "").strip(),
    }


def index_case_base(context: DesktopContext) -> dict[str, Any]:
    return index_all_cases(
        context.db_path,
        context.case_base_paths["knowledge_base"],
        context.runtime_dirs["vectors"],
    )


def case_base_signature(context: DesktopContext) -> str:
    knowledge_base = context.case_base_paths["knowledge_base"]
    vector_config = load_vector_config()
    payload = {
        "case_base": fingerprint_case_base(knowledge_base),
        "embedding_provider": vector_config.provider,
        "collection": vector_config.collection,
        "local_dimensions": vector_config.local_dimensions,
        "huggingface_model": vector_config.huggingface_model,
        "huggingface_url": vector_config.huggingface_url,
    }
    return json.dumps(payload, sort_keys=True)


def case_base_overview(context: DesktopContext) -> dict[str, Any]:
    return {
        "case_dirs": list_case_dirs(context.case_base_paths["knowledge_base"]),
        "indexed_cases": list_indexed_cases(context.db_path),
        "vector_config": load_vector_config(),
    }


def generate_metadata_and_reindex(context: DesktopContext, fill_existing_empty: bool = True) -> dict[str, Any]:
    metadata_result = generate_metadata_files(
        context.case_base_paths["knowledge_base"],
        fill_existing_empty=fill_existing_empty,
    )
    index_result = index_case_base(context)
    return {"metadata": metadata_result, "index": index_result}


def history_rows(context: DesktopContext) -> list[dict[str, Any]]:
    return list_analyses(context.db_path)


def load_prompt(context: DesktopContext) -> str:
    return load_base_instructions(context.case_base_paths["instructions"])


def save_prompt(context: DesktopContext, content: str) -> str:
    save_base_instructions(context.case_base_paths["instructions"], content)
    return prompt_hash(content)


def build_record(
    *,
    project_info: dict[str, str],
    result: dict[str, Any],
    pdf_summary: dict[str, Any],
    pdf_name: str,
    upload_path: Path,
    report_paths: dict[str, Path],
    related_cases: list[dict[str, Any]],
    base_prompt: str,
    base_prompt_path: Path,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "user_name": project_info.get("usuario", ""),
        "customer": project_info.get("cliente", ""),
        "document": project_info.get("documento", ""),
        "project": project_info.get("projeto", ""),
        "revision": project_info.get("revisao", ""),
        "provider": result.get("provider", ""),
        "model": result.get("model", ""),
        "status": result.get("status", ""),
        "overall_risk": result.get("overall_risk", ""),
        "findings_count": result.get("findings_count", 0),
        "max_severity": result.get("max_severity", ""),
        "pdf_name": pdf_name,
        "upload_path": str(upload_path),
        "report_xlsx_path": str(report_paths["xlsx"]),
        "report_md_path": str(report_paths["md"]),
        "report_pdf_path": str(report_paths["pdf"]),
        "related_cases_json": json.dumps(related_cases, ensure_ascii=False),
        "base_prompt_hash": prompt_hash(base_prompt),
        "base_prompt_path": str(base_prompt_path),
        "result_json": json.dumps(result, ensure_ascii=False),
        "pdf_summary_json": json.dumps(
            {
                "file_name": pdf_summary.get("file_name"),
                "pages_count": pdf_summary.get("pages_count"),
                "metadata": pdf_summary.get("metadata"),
                "inferred": pdf_summary.get("inferred"),
                "pages": pdf_summary.get("pages"),
                "critical_pages": pdf_summary.get("critical_pages"),
                "warnings": pdf_summary.get("warnings"),
            },
            ensure_ascii=False,
        ),
    }
