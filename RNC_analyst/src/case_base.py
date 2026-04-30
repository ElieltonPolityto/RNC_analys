from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .pdf_tools import build_text_brief, normalize_text, parse_pdf_bytes
from .vector_store import query_vector_cases, sync_vector_index


CASE_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS rnc_cases (
    case_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    title TEXT,
    customer TEXT,
    document TEXT,
    order_number TEXT,
    project TEXT,
    revision TEXT,
    rnc_date TEXT,
    rnc_type TEXT,
    severity TEXT,
    root_cause TEXT,
    corrective_action TEXT,
    preventive_action TEXT,
    related_pages_json TEXT,
    tags_json TEXT,
    case_dir TEXT NOT NULL,
    project_file TEXT,
    rnc_file TEXT,
    observations_file TEXT,
    summary_text TEXT,
    search_text TEXT,
    keywords_json TEXT,
    file_fingerprint TEXT,
    indexed_at TEXT NOT NULL,
    errors_json TEXT
);
"""


CASE_ID_PATTERN = re.compile(r"^ID[\w.-]+$", re.I)
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".json"}
SUPPORTED_TABLE_EXTENSIONS = {".csv", ".xlsx", ".xls"}
SUPPORTED_EXTENSIONS = {".pdf", *SUPPORTED_TEXT_EXTENSIONS, *SUPPORTED_TABLE_EXTENSIONS}
PROJECT_HINTS = ("projeto", "project", "desenho", "eletrico", "eltrico", "qpl", "painel")
RNC_HINTS = ("rnc", "nao_conformidade", "nao-conformidade", "conformidade", "relatorio", "relatorio_rnc")
METADATA_TEMPLATE = {
    "case_id": "",
    "cliente": "",
    "documento": "",
    "pedido": "",
    "projeto": "",
    "revisao": "",
    "data_rnc": "",
    "tipo_rnc": "",
    "severidade": "",
    "causa_raiz": "",
    "acao_corretiva": "",
    "acao_preventiva": "",
    "paginas_relacionadas": [],
    "tags_componentes": [],
    "observacoes": "",
}
STOPWORDS = {
    "a",
    "as",
    "ao",
    "aos",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "para",
    "por",
    "que",
    "um",
    "uma",
    "projeto",
    "pagina",
    "paginas",
    "folha",
    "cliente",
    "documento",
}


DEFAULT_INSTRUCTIONS = """Voce e um assistente de revisao preventiva de RNC para projetos eletricos industriais.

Use a base historica como memoria tecnica: quando um projeto atual parecer com um caso anterior, verifique se o mesmo padrao de falha pode aparecer novamente.
Nao invente falhas; cite casos historicos apenas quando houver evidencia real de semelhanca.
"""


def ensure_case_base(base_dir: Path) -> dict[str, Path]:
    knowledge_base = base_dir / "knowledge_base"
    prompts = base_dir / "prompts"
    knowledge_base.mkdir(parents=True, exist_ok=True)
    prompts.mkdir(parents=True, exist_ok=True)

    instructions_path = prompts / "instrucoes_base.txt"
    if not instructions_path.exists():
        instructions_path.write_text(DEFAULT_INSTRUCTIONS, encoding="utf-8")

    readme_path = knowledge_base / "_README_LOCAL.txt"
    if not readme_path.exists():
        readme_path.write_text(
            "\n".join(
                [
                    "Coloque aqui seus casos reais de RNC.",
                    "Use uma subpasta por caso: ID01, ID02, ID03.",
                    "Dentro de cada pasta, coloque o projeto, a RNC, metadata.json e observacoes.txt.",
                    "Arquivos nesta pasta ficam fora do Git por seguranca.",
                ]
            ),
            encoding="utf-8",
        )

    return {"knowledge_base": knowledge_base, "instructions": instructions_path}


def load_base_instructions(path: Path) -> str:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_INSTRUCTIONS, encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def save_base_instructions(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def prompt_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:16]


def init_case_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(CASE_TABLE_SCHEMA)
        conn.commit()


def list_case_dirs(knowledge_base: Path) -> list[Path]:
    if not knowledge_base.exists():
        return []
    return sorted(
        [
            path
            for path in knowledge_base.iterdir()
            if path.is_dir() and CASE_ID_PATTERN.match(path.name) and path.name != "ID_TEMPLATE"
        ],
        key=lambda item: item.name.lower(),
    )


def index_all_cases(db_path: Path, knowledge_base: Path, vector_dir: Path | None = None) -> dict[str, Any]:
    init_case_tables(db_path)
    results = []
    case_dirs = list_case_dirs(knowledge_base)
    for case_dir in case_dirs:
        results.append(index_case(db_path, case_dir))
    pruned = prune_missing_cases(db_path, [path.name for path in case_dirs])
    vector_index = None
    if vector_dir is not None:
        vector_index = sync_vector_index(vector_dir, load_vector_records(db_path))
    return {
        "indexed_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "ok": sum(1 for item in results if item.get("status") == "ok"),
        "warning": sum(1 for item in results if item.get("status") == "warning"),
        "error": sum(1 for item in results if item.get("status") == "error"),
        "pruned": pruned,
        "vector_index": vector_index,
        "results": results,
    }


def fingerprint_case_base(knowledge_base: Path) -> str:
    hasher = hashlib.sha256()
    for case_dir in list_case_dirs(knowledge_base):
        hasher.update(case_dir.name.encode("utf-8"))
        hasher.update(fingerprint_case(case_dir).encode("ascii"))
    return hasher.hexdigest()


def index_case(db_path: Path, case_dir: Path) -> dict[str, Any]:
    case_id = case_dir.name
    metadata = load_case_metadata(case_dir)
    files = discover_case_files(case_dir)
    errors: list[str] = []

    project_text = ""
    rnc_text = ""
    for file_path in files["project_files"]:
        extracted = extract_file_text(file_path)
        project_text += f"\n\n--- {file_path.name} ---\n{extracted['text']}"
        errors.extend(extracted["errors"])

    for file_path in files["rnc_files"]:
        extracted = extract_file_text(file_path)
        rnc_text += f"\n\n--- {file_path.name} ---\n{extracted['text']}"
        errors.extend(extracted["errors"])

    observation_text = read_observations(case_dir)
    if not project_text.strip():
        errors.append("Nenhum arquivo de projeto suportado encontrado ou texto vazio.")
    if not rnc_text.strip() and not observation_text.strip():
        errors.append("Nenhum conteudo de RNC/observacoes encontrado.")

    summary_text = build_case_summary(
        case_id=case_id,
        metadata=metadata,
        project_text=project_text,
        rnc_text=rnc_text,
        observation_text=observation_text,
    )
    search_text = "\n".join(
        [
            json.dumps(metadata, ensure_ascii=False),
            project_text[:40000],
            rnc_text[:40000],
            observation_text,
        ]
    )
    keywords = extract_keywords(search_text)
    status = "ok"
    if errors:
        status = "warning" if project_text.strip() or rnc_text.strip() or observation_text.strip() else "error"

    record = {
        "case_id": case_id,
        "status": status,
        "title": metadata.get("titulo") or metadata.get("tipo_rnc") or case_id,
        "customer": metadata.get("cliente", ""),
        "document": metadata.get("documento", ""),
        "order_number": metadata.get("pedido", ""),
        "project": metadata.get("projeto", ""),
        "revision": metadata.get("revisao", ""),
        "rnc_date": metadata.get("data_rnc", ""),
        "rnc_type": metadata.get("tipo_rnc", ""),
        "severity": metadata.get("severidade", ""),
        "root_cause": metadata.get("causa_raiz", ""),
        "corrective_action": metadata.get("acao_corretiva", ""),
        "preventive_action": metadata.get("acao_preventiva", ""),
        "related_pages_json": json.dumps(metadata.get("paginas_relacionadas", []), ensure_ascii=False),
        "tags_json": json.dumps(metadata.get("tags_componentes", []), ensure_ascii=False),
        "case_dir": str(case_dir),
        "project_file": "; ".join(str(path) for path in files["project_files"]),
        "rnc_file": "; ".join(str(path) for path in files["rnc_files"]),
        "observations_file": str(case_dir / "observacoes.txt") if (case_dir / "observacoes.txt").exists() else "",
        "summary_text": summary_text,
        "search_text": search_text,
        "keywords_json": json.dumps(keywords, ensure_ascii=False),
        "file_fingerprint": fingerprint_case(case_dir),
        "indexed_at": datetime.now().isoformat(timespec="seconds"),
        "errors_json": json.dumps(errors, ensure_ascii=False),
    }
    upsert_case(db_path, record)
    return {"case_id": case_id, "status": status, "errors": errors}


def load_case_metadata(case_dir: Path) -> dict[str, Any]:
    metadata_path = case_dir / "metadata.json"
    if not metadata_path.exists():
        return {"case_id": case_dir.name}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"case_id": case_dir.name, "metadata_error": str(exc)}
    payload.setdefault("case_id", case_dir.name)
    return payload


def generate_metadata_files(knowledge_base: Path, *, fill_existing_empty: bool = True) -> dict[str, Any]:
    results = [
        generate_case_metadata_file(case_dir, fill_existing_empty=fill_existing_empty)
        for case_dir in list_case_dirs(knowledge_base)
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "created": sum(1 for item in results if item.get("status") == "created"),
        "updated": sum(1 for item in results if item.get("status") == "updated"),
        "skipped": sum(1 for item in results if item.get("status") == "skipped"),
        "error": sum(1 for item in results if item.get("status") == "error"),
        "results": results,
    }


def generate_case_metadata_file(case_dir: Path, *, fill_existing_empty: bool = True) -> dict[str, Any]:
    metadata_path = case_dir / "metadata.json"
    generated = infer_case_metadata(case_dir)
    generated["case_id"] = case_dir.name

    if metadata_path.exists():
        try:
            current = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "case_id": case_dir.name,
                "status": "error",
                "message": f"metadata.json invalido: {exc}",
                "metadata_path": str(metadata_path),
            }

        if not fill_existing_empty:
            return {
                "case_id": case_dir.name,
                "status": "skipped",
                "message": "metadata.json ja existe.",
                "metadata_path": str(metadata_path),
            }

        merged = merge_metadata_empty_fields(current, generated)
        if merged == current:
            return {
                "case_id": case_dir.name,
                "status": "skipped",
                "message": "metadata.json ja estava completo ou sem novos dados inferidos.",
                "metadata_path": str(metadata_path),
            }
        metadata_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {
            "case_id": case_dir.name,
            "status": "updated",
            "message": "Campos vazios preenchidos.",
            "metadata_path": str(metadata_path),
        }

    metadata_path.write_text(json.dumps(generated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "case_id": case_dir.name,
        "status": "created",
        "message": "metadata.json criado automaticamente.",
        "metadata_path": str(metadata_path),
    }


def infer_case_metadata(case_dir: Path) -> dict[str, Any]:
    files = discover_case_files(case_dir)
    errors: list[str] = []
    project_text = collect_files_text(files["project_files"], errors)
    rnc_text = collect_files_text(files["rnc_files"], errors)
    observation_text = read_observations(case_dir)
    combined_text = "\n".join([project_text, rnc_text, observation_text])
    project_inferred = infer_project_metadata_from_pdfs(files["project_files"], errors)
    text_inferred = infer_project_metadata_from_text(combined_text)

    metadata = build_empty_metadata(case_dir.name)
    metadata.update(
        {
            "cliente": first_value(project_inferred.get("cliente"), text_inferred.get("cliente")),
            "documento": first_value(project_inferred.get("documento"), text_inferred.get("documento")),
            "pedido": first_value(project_inferred.get("pedido"), text_inferred.get("pedido")),
            "projeto": first_value(project_inferred.get("projeto"), text_inferred.get("projeto")),
            "revisao": first_value(project_inferred.get("revisao"), text_inferred.get("revisao")),
            "data_rnc": infer_rnc_date(rnc_text or combined_text),
            "tipo_rnc": infer_rnc_type(rnc_text or combined_text),
            "severidade": infer_severity(rnc_text or combined_text),
            "causa_raiz": extract_labeled_value(
                rnc_text,
                ["causa raiz", "causa", "motivo", "origem da falha", "descricao da nao conformidade"],
            ),
            "acao_corretiva": extract_labeled_value(
                rnc_text,
                ["acao corretiva", "correcao", "disposicao", "tratativa", "acao tomada"],
            ),
            "acao_preventiva": extract_labeled_value(
                rnc_text,
                ["acao preventiva", "prevencao", "acao para evitar recorrencia", "recomendacao"],
            ),
            "paginas_relacionadas": infer_related_pages(combined_text),
            "tags_componentes": infer_component_tags(combined_text),
            "observacoes": build_generated_observation(files, errors, observation_text),
            "metadata_gerado_por": "RNC Analyst",
            "metadata_gerado_em": datetime.now().isoformat(timespec="seconds"),
        }
    )
    return metadata


def build_empty_metadata(case_id: str) -> dict[str, Any]:
    metadata = dict(METADATA_TEMPLATE)
    metadata["case_id"] = case_id
    return metadata


def collect_files_text(file_paths: list[Path], errors: list[str]) -> str:
    parts = []
    for file_path in file_paths:
        extracted = extract_file_text(file_path)
        parts.append(f"\n\n--- {file_path.name} ---\n{extracted['text'][:30000]}")
        errors.extend(extracted["errors"])
    return "\n".join(parts)


def infer_project_metadata_from_pdfs(file_paths: list[Path], errors: list[str]) -> dict[str, str]:
    inferred: dict[str, str] = {}
    for file_path in file_paths:
        if file_path.suffix.lower() != ".pdf":
            continue
        try:
            summary = parse_pdf_bytes(file_path.read_bytes(), file_path.name)
            merge_non_empty(inferred, summary.get("inferred", {}))
        except Exception as exc:
            errors.append(f"Falha ao inferir metadados de {file_path.name}: {exc}")
    return inferred


def infer_project_metadata_from_text(text: str) -> dict[str, str]:
    metadata = extract_metadata_from_labels(text)
    inferred = parse_text_project_identifiers(text)
    merge_non_empty(metadata, inferred)
    return metadata


def extract_metadata_from_labels(text: str) -> dict[str, str]:
    return {
        "cliente": extract_labeled_value(text, ["cliente", "customer"]),
        "documento": extract_labeled_value(text, ["documento", "doc", "codigo documento", "desenho"]),
        "pedido": extract_labeled_value(text, ["pedido", "ordem", "op", "os"]),
        "projeto": extract_labeled_value(text, ["projeto", "project", "painel"]),
        "revisao": extract_labeled_value(text, ["revisao", "rev"]),
    }


def parse_text_project_identifiers(text: str) -> dict[str, str]:
    document = first_match_regex(text, r"\bR\d{2}[A-Z]{2}\d{3,}[A-Z]?\.\d{2}\b")
    order = first_match_regex(text, r"\b\d{6}\b")
    project = first_match_regex(text, r"\bQ[A-Z]{1,3}\d+\b")
    revision = ""
    rev_match = re.search(r"\bREV\.?\s*([A-Z0-9-]{1,4})\b", normalize_text(text))
    if rev_match:
        revision = rev_match.group(1)
    return {"documento": document, "pedido": order, "projeto": project, "revisao": revision}


def merge_metadata_empty_fields(current: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key, default_value in METADATA_TEMPLATE.items():
        merged.setdefault(key, default_value)
    for key in METADATA_TEMPLATE:
        value = generated.get(key)
        if is_empty_metadata_value(merged.get(key)) and not is_empty_metadata_value(value):
            merged[key] = value
    merged["case_id"] = generated["case_id"]
    return merged


def is_empty_metadata_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def merge_non_empty(target: dict[str, str], source: dict[str, str]) -> None:
    for key, value in source.items():
        if value and not target.get(key):
            target[key] = str(value).strip()


def first_value(*values: Any) -> str:
    for value in values:
        if value:
            return str(value).strip()
    return ""


def extract_labeled_value(text: str, labels: list[str], max_chars: int = 180) -> str:
    normalized_labels = {normalize_text(label).lower() for label in labels}
    for line in (text or "").splitlines():
        if not any(separator in line for separator in [":", "=", "-"]):
            continue
        parts = re.split(r"\s*[:=\-]\s*", line, maxsplit=1)
        if len(parts) != 2:
            continue
        key, value = parts
        normalized_key = normalize_text(key).lower()
        if normalized_key in normalized_labels:
            return clean_metadata_value(value, max_chars=max_chars)
    return ""


def clean_metadata_value(value: str, *, max_chars: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" :-\t")
    return value[:max_chars].strip()


def infer_rnc_date(text: str) -> str:
    return first_match_regex(text, r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b") or first_match_regex(
        text, r"\b20\d{2}-\d{2}-\d{2}\b"
    )


def first_match_regex(value: str, pattern: str) -> str:
    match = re.search(pattern, value or "", flags=re.I)
    return match.group(0).strip() if match else ""


def infer_rnc_type(text: str) -> str:
    normalized = normalize_text(text).lower()
    categories = [
        ("Cotas/dimensoes", ("cota", "dimensao", "dimensional")),
        ("Furacao", ("furacao", "furo", "recorte")),
        ("Layout", ("layout", "placa", "porta", "disposicao")),
        ("Identificacao/etiquetas", ("identificacao", "etiqueta", "tag", "anilha")),
        ("Bornes/cabos", ("borne", "cabo", "conexao", "origem", "destino")),
        ("Componente faltante/divergente", ("componente", "faltante", "ausente", "divergente")),
        ("Documentacao/revisao", ("documentacao", "revisao", "folha", "lista de desenho")),
        ("Comando eletrico", ("comando", "intertravamento", "selo", "emergencia")),
    ]
    found = [name for name, terms in categories if any(term in normalized for term in terms)]
    labeled = extract_labeled_value(text, ["tipo de rnc", "tipo", "categoria"])
    if labeled and labeled not in found:
        found.insert(0, labeled)
    return "; ".join(found[:4])


def infer_severity(text: str) -> str:
    normalized = normalize_text(text).lower()
    if any(term in normalized for term in ["critico", "grave", "alta", "parada", "seguranca"]):
        return "alta"
    if any(term in normalized for term in ["media", "moderado", "retrabalho", "duvida"]):
        return "media"
    if any(term in normalized for term in ["baixa", "menor", "observacao"]):
        return "baixa"
    return ""


def infer_related_pages(text: str, limit: int = 20) -> list[int]:
    normalized = normalize_text(text).lower()
    pages: list[int] = []
    for match in re.finditer(r"\b(?:pagina|pag|folha)\D{0,8}(\d{1,4})\b", normalized):
        page = int(match.group(1))
        if 0 < page < 2000 and page not in pages:
            pages.append(page)
        if len(pages) >= limit:
            break
    return pages


def infer_component_tags(text: str, limit: int = 50) -> list[str]:
    normalized = normalize_text(text)
    pattern = r"\b(?:QF|DJ|KM|KA|K|RT|F|FU|M|IHM|CLP|PLC|INV|SS|TR|TB|X|B|S|HL|HS|PS|CR)\s*[-.]?\s*\d+[A-Z0-9.-]*\b"
    tags: list[str] = []
    for match in re.finditer(pattern, normalized):
        tag = re.sub(r"\s+", "", match.group(0))
        if tag not in tags:
            tags.append(tag)
        if len(tags) >= limit:
            break
    return tags


def build_generated_observation(files: dict[str, list[Path]], errors: list[str], observation_text: str) -> str:
    parts = [
        "Metadados gerados automaticamente pelo RNC Analyst. Revise os campos antes de usar como fonte oficial."
    ]
    if files["project_files"]:
        parts.append("Projeto(s): " + "; ".join(path.name for path in files["project_files"]))
    if files["rnc_files"]:
        parts.append("RNC(s): " + "; ".join(path.name for path in files["rnc_files"]))
    if observation_text.strip():
        parts.append("Observacoes existentes consideradas.")
    if errors:
        parts.append("Avisos: " + "; ".join(errors[:5]))
    return " ".join(parts)


def discover_case_files(case_dir: Path) -> dict[str, list[Path]]:
    supported_files = [
        path
        for path in sorted(case_dir.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    project_files: list[Path] = []
    rnc_files: list[Path] = []
    other_files: list[Path] = []

    for path in supported_files:
        normalized = normalize_text(path.stem).lower()
        if path.name.lower() in {"metadata.json", "observacoes.txt"}:
            continue
        if any(hint in normalized for hint in RNC_HINTS):
            rnc_files.append(path)
        elif any(hint in normalized for hint in PROJECT_HINTS):
            project_files.append(path)
        else:
            other_files.append(path)

    if not project_files and other_files:
        project_files.append(other_files.pop(0))
    if not rnc_files and other_files:
        rnc_files.extend(other_files)

    return {"project_files": project_files, "rnc_files": rnc_files, "other_files": other_files}


def extract_file_text(file_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".pdf":
            summary = parse_pdf_bytes(file_path.read_bytes(), file_path.name)
            text = build_text_brief(summary, max_chars=60000)
        elif suffix in SUPPORTED_TEXT_EXTENSIONS:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        elif suffix == ".csv":
            text = read_csv_text(file_path)
        elif suffix in {".xlsx", ".xls"}:
            text = read_excel_text(file_path)
        else:
            text = ""
            errors.append(f"Formato nao suportado: {file_path.name}")
    except Exception as exc:
        text = ""
        errors.append(f"Falha ao ler {file_path.name}: {exc}")
    return {"text": text, "errors": errors}


def read_observations(case_dir: Path) -> str:
    observations_path = case_dir / "observacoes.txt"
    if observations_path.exists():
        return observations_path.read_text(encoding="utf-8", errors="replace")
    return ""


def read_csv_text(file_path: Path) -> str:
    rows: list[str] = []
    with file_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for index, row in enumerate(reader):
            if index >= 300:
                break
            rows.append(" | ".join(row))
    return "\n".join(rows)


def read_excel_text(file_path: Path) -> str:
    sheets = pd.read_excel(file_path, sheet_name=None, dtype=str, nrows=300)
    parts: list[str] = []
    for sheet_name, frame in sheets.items():
        parts.append(f"--- ABA: {sheet_name} ---")
        parts.append(frame.fillna("").to_csv(index=False, sep=";"))
    return "\n".join(parts)


def build_case_summary(
    *,
    case_id: str,
    metadata: dict[str, Any],
    project_text: str,
    rnc_text: str,
    observation_text: str,
) -> str:
    fields = [
        f"Caso: {case_id}",
        f"Cliente: {metadata.get('cliente', '')}",
        f"Documento: {metadata.get('documento', '')}",
        f"Pedido: {metadata.get('pedido', '')}",
        f"Projeto: {metadata.get('projeto', '')}",
        f"Revisao: {metadata.get('revisao', '')}",
        f"Tipo de RNC: {metadata.get('tipo_rnc', '')}",
        f"Severidade: {metadata.get('severidade', '')}",
        f"Causa raiz: {metadata.get('causa_raiz', '')}",
        f"Acao corretiva: {metadata.get('acao_corretiva', '')}",
        f"Acao preventiva: {metadata.get('acao_preventiva', '')}",
        f"Paginas relacionadas: {metadata.get('paginas_relacionadas', [])}",
        f"Tags/componentes: {metadata.get('tags_componentes', [])}",
        "",
        "Observacoes humanas:",
        observation_text[:6000],
        "",
        "Trecho da RNC:",
        rnc_text[:9000],
        "",
        "Trecho do projeto problematico:",
        project_text[:9000],
    ]
    return "\n".join(fields)


def extract_keywords(text: str, limit: int = 60) -> list[str]:
    tokens = tokenize(text)
    counts = Counter(tokens)
    return [token for token, _ in counts.most_common(limit)]


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text).lower()
    tokens = re.findall(r"[a-z0-9][a-z0-9_.-]{2,}", normalized)
    return [token for token in tokens if token not in STOPWORDS and len(token) >= 3]


def fingerprint_case(case_dir: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(case_dir.rglob("*"), key=lambda item: str(item).lower()):
        if path.is_file():
            stat = path.stat()
            hasher.update(str(path.relative_to(case_dir)).encode("utf-8"))
            hasher.update(str(stat.st_size).encode("ascii"))
            hasher.update(str(int(stat.st_mtime)).encode("ascii"))
    return hasher.hexdigest()


def upsert_case(db_path: Path, record: dict[str, Any]) -> None:
    columns = list(record.keys())
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "case_id")
    with sqlite3.connect(db_path) as conn:
        conn.execute(CASE_TABLE_SCHEMA)
        conn.execute(
            f"""
            INSERT INTO rnc_cases ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(case_id) DO UPDATE SET {updates}
            """,
            [record[column] for column in columns],
        )
        conn.commit()


def prune_missing_cases(db_path: Path, current_case_ids: list[str]) -> int:
    init_case_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        if current_case_ids:
            placeholders = ", ".join("?" for _ in current_case_ids)
            cursor = conn.execute(
                f"DELETE FROM rnc_cases WHERE case_id NOT IN ({placeholders})",
                current_case_ids,
            )
        else:
            cursor = conn.execute("DELETE FROM rnc_cases")
        conn.commit()
        return int(cursor.rowcount)


def list_indexed_cases(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    init_case_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT case_id, status, title, customer, document, project, revision,
                   rnc_type, severity, indexed_at, project_file, rnc_file, errors_json
            FROM rnc_cases
            ORDER BY case_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def load_vector_records(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    init_case_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT case_id, status, title, customer, document, project, revision,
                   rnc_type, severity, root_cause, corrective_action,
                   preventive_action, summary_text, search_text, keywords_json,
                   file_fingerprint
            FROM rnc_cases
            WHERE status IN ('ok', 'warning')
            """
        ).fetchall()
    return [dict(row) for row in rows]


def search_similar_cases(
    db_path: Path,
    *,
    pdf_summary: dict[str, Any],
    project_info: dict[str, str],
    limit: int = 5,
    vector_dir: Path | None = None,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    init_case_tables(db_path)
    query_text = build_case_query_text(pdf_summary, project_info)
    query_counter = Counter(tokenize(query_text))
    if not query_counter:
        return []

    rows = load_vector_records(db_path)
    row_by_id = {row["case_id"]: row for row in rows}

    matches = []
    seen: set[str] = set()
    if vector_dir is not None and limit > 0:
        vector_result = query_vector_cases(vector_dir, query_text, max(limit * 3, 10))
        for vector_match in vector_result.get("matches", []):
            candidate = row_by_id.get(vector_match.get("case_id", ""))
            if not candidate:
                continue
            match = build_ranked_match(
                candidate,
                query_counter,
                project_info,
                pdf_summary,
                vector_score=float(vector_match.get("vector_score") or 0),
                vector_distance=vector_match.get("vector_distance"),
            )
            if match["score"] <= 0:
                continue
            matches.append(match)
            seen.add(candidate["case_id"])

    for candidate in rows:
        if len(matches) >= max(limit * 2, limit) and vector_dir is not None:
            break
        if candidate["case_id"] in seen:
            continue
        match = build_ranked_match(candidate, query_counter, project_info, pdf_summary)
        if match["score"] <= 0:
            continue
        matches.append(match)

    return sorted(matches, key=lambda item: item["score"], reverse=True)[:limit]


def build_case_query_text(pdf_summary: dict[str, Any], project_info: dict[str, str]) -> str:
    return "\n".join(
        [
            json.dumps(project_info, ensure_ascii=False),
            json.dumps(pdf_summary.get("inferred", {}), ensure_ascii=False),
            build_text_brief(pdf_summary, max_chars=50000),
        ]
    )


def build_ranked_match(
    candidate: dict[str, Any],
    query_counter: Counter[str],
    project_info: dict[str, str],
    pdf_summary: dict[str, Any],
    *,
    vector_score: float | None = None,
    vector_distance: float | None = None,
) -> dict[str, Any]:
    candidate_counter = Counter(tokenize(candidate.get("search_text") or ""))
    lexical_score = cosine_similarity(query_counter, candidate_counter)
    metadata_score = metadata_similarity(project_info, pdf_summary.get("inferred", {}), candidate)
    if vector_score is None:
        score = min(1.0, lexical_score * 0.78 + metadata_score * 0.22)
        retrieval_method = "lexical"
    else:
        score = min(1.0, vector_score * 0.68 + lexical_score * 0.20 + metadata_score * 0.12)
        retrieval_method = "vetorial"
    keywords = json.loads(candidate.get("keywords_json") or "[]")
    match = {
        "case_id": candidate["case_id"],
        "score": round(score, 4),
        "similarity": similarity_label(score),
        "retrieval_method": retrieval_method,
        "title": candidate.get("title") or candidate["case_id"],
        "customer": candidate.get("customer", ""),
        "document": candidate.get("document", ""),
        "project": candidate.get("project", ""),
        "revision": candidate.get("revision", ""),
        "rnc_type": candidate.get("rnc_type", ""),
        "severity": candidate.get("severity", ""),
        "root_cause": candidate.get("root_cause", ""),
        "corrective_action": candidate.get("corrective_action", ""),
        "preventive_action": candidate.get("preventive_action", ""),
        "keywords": keywords[:15],
        "summary_text": (candidate.get("summary_text") or "")[:7000],
    }
    if vector_score is not None:
        match["vector_score"] = round(vector_score, 4)
        match["vector_distance"] = vector_distance
    return match


def cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def metadata_similarity(
    project_info: dict[str, str], inferred: dict[str, str], candidate: dict[str, Any]
) -> float:
    pairs = [
        ((project_info.get("cliente") or inferred.get("cliente", "")), candidate.get("customer", "")),
        ((project_info.get("documento") or inferred.get("documento", "")), candidate.get("document", "")),
        ((project_info.get("projeto") or inferred.get("projeto", "")), candidate.get("project", "")),
    ]
    points = 0
    possible = 0
    for current, historical in pairs:
        if not current or not historical:
            continue
        possible += 1
        if normalize_text(current) == normalize_text(historical):
            points += 1
        elif normalize_text(current) in normalize_text(historical) or normalize_text(historical) in normalize_text(current):
            points += 0.5
    return points / possible if possible else 0.0


def similarity_label(score: float) -> str:
    if score >= 0.45:
        return "alta"
    if score >= 0.25:
        return "media"
    return "baixa"


def build_cases_prompt_context(cases: list[dict[str, Any]]) -> str:
    if not cases:
        return "Nenhum caso historico semelhante foi encontrado na base local."
    blocks = []
    for case in cases:
        blocks.append(
            "\n".join(
                [
                    f"Caso historico {case['case_id']} ({case['similarity']} similaridade, score {case['score']}):",
                    f"Metodo de busca: {case.get('retrieval_method') or 'lexical'}",
                    f"Cliente: {case.get('customer') or 'nao informado'}",
                    f"Documento/projeto: {case.get('document') or '-'} / {case.get('project') or '-'}",
                    f"Tipo de RNC: {case.get('rnc_type') or 'nao informado'}",
                    f"Severidade historica: {case.get('severity') or 'nao informada'}",
                    f"Causa raiz: {case.get('root_cause') or 'nao informada'}",
                    f"Acao preventiva: {case.get('preventive_action') or 'nao informada'}",
                    f"Palavras-chave: {', '.join(case.get('keywords') or [])}",
                    "Resumo do caso:",
                    case.get("summary_text", ""),
                ]
            )
        )
    return "\n\n".join(blocks)
