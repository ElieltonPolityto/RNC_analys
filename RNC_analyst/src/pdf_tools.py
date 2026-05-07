from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader


CRITICAL_KEYWORDS = [
    "COMPONENTES NA PLACA",
    "COTAS",
    "LAYOUT",
    "ETIQUETAS",
    "IDENTIFICACAO DOS CABOS",
    "IDENTIFICACAO",
    "BORNE",
]

REVIEW_KEYWORDS = [
    "ALIMENTACAO",
    "COMANDO",
]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().upper()


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem).strip("._")
    suffix = Path(name).suffix.lower() or ".pdf"
    if suffix != ".pdf":
        suffix = ".pdf"
    return f"{stem or 'projeto'}{suffix}"


def ensure_runtime_dirs(base_dir: Path) -> dict[str, Path]:
    paths = {
        "data": base_dir / "data",
        "uploads": base_dir / "uploads",
        "reports": base_dir / "reports",
        "vectors": base_dir / "data" / "chroma",
        "knowledge_base": base_dir / "knowledge_base",
        "prompts": base_dir / "prompts",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def save_uploaded_pdf(file_bytes: bytes, original_name: str, uploads_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_name = safe_filename(original_name)
    target = uploads_dir / f"{timestamp}_{uuid.uuid4().hex[:8]}_{file_name}"
    target.write_bytes(file_bytes)
    return target


def extract_metadata(summary_text: str, metadata: dict[str, str]) -> dict[str, str]:
    raw = summary_text or ""
    normalized = normalize_text(raw)

    document = _first_match(raw, r"\bR\d{2}[A-Z]{2}\d{3,}[A-Z]?\.\d{2}\b")
    order = _first_match(raw, r"\b\d{6}\b")
    project = _first_match(raw, r"\bQ[A-Z]{1,3}\d+\b")
    title = metadata.get("/Title", "").strip()

    customer = ""
    if order:
        customer_match = re.search(r"([A-Z][A-Z ]{3,} [A-Z][A-Z ]{2,})" + re.escape(order), raw)
        if customer_match:
            customer = customer_match.group(1).strip()
            customer = re.sub(r"^[A-Z0-9. -]*?(?=[A-Z]{3,} [A-Z]{3,}$)", "", customer).strip()

    revision = ""
    rev_match = re.search(r"\bREV\.?\s*([A-Z0-9-]{1,4})\b", normalized)
    if rev_match:
        revision = rev_match.group(1)

    return {
        "cliente": customer,
        "documento": document or title,
        "pedido": order,
        "projeto": project,
        "revisao": revision,
    }


def parse_pdf_bytes(file_bytes: bytes, file_name: str) -> dict[str, Any]:
    try:
        reader = PdfReader(BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError(f"Nao foi possivel abrir o PDF '{file_name}'. O arquivo pode estar corrompido.") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass
        if reader.is_encrypted:
            raise ValueError(f"O PDF '{file_name}' esta protegido por senha e nao pode ser analisado.")

    metadata = {str(k): str(v) for k, v in (reader.metadata or {}).items()}
    pages: list[dict[str, Any]] = []
    text_parts: list[str] = []
    warnings: list[str] = []

    for index, page in enumerate(reader.pages):
        text = ""
        extraction_error = ""
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover - depends on PDF internals
            extraction_error = str(exc)
            warnings.append(f"Pagina {index + 1}: falha ao extrair texto ({exc})")

        normalized = normalize_text(text)
        description = detect_page_description(normalized)
        text_parts.append(f"\n--- PAGINA {index + 1} ---\n{text[:5000]}")

        mediabox = page.mediabox
        pages.append(
            {
                "page": index + 1,
                "text_chars": len(text),
                "description": description,
                "width_pt": float(mediabox.width),
                "height_pt": float(mediabox.height),
                "rotation": int(page.get("/Rotate", 0) or 0),
                "is_text_sparse": len(text) < 500,
                "is_critical": is_critical_page(normalized, len(text), index + 1),
                "extraction_error": extraction_error,
            }
        )

    full_text = "\n".join(text_parts)
    inferred = extract_metadata(full_text[:20000], metadata)
    critical_pages = [p["page"] for p in pages if p["is_critical"]]

    return {
        "file_name": file_name,
        "pages_count": len(pages),
        "metadata": metadata,
        "inferred": inferred,
        "pages": pages,
        "critical_pages": critical_pages,
        "text": full_text,
        "warnings": warnings,
    }


def detect_page_description(normalized_text: str) -> str:
    for keyword in CRITICAL_KEYWORDS + REVIEW_KEYWORDS:
        if keyword in normalized_text:
            return keyword

    candidates = [
        "LISTA DE DESENHO",
        "LEGENDA",
        "INSTRUCOES",
        "TABELA DE TORQUE",
        "SETAGEM",
    ]
    for keyword in candidates:
        if keyword in normalized_text:
            return keyword
    return ""


def is_critical_page(normalized_text: str, text_chars: int, page_number: int) -> bool:
    if page_number >= 8 and any(keyword in normalized_text for keyword in CRITICAL_KEYWORDS):
        return True
    if page_number >= 50 and text_chars < 800:
        return True
    if page_number >= 8 and any(keyword in normalized_text for keyword in REVIEW_KEYWORDS) and text_chars < 650:
        return True
    return False


def build_text_brief(summary: dict[str, Any], max_chars: int = 28000) -> str:
    metadata = summary.get("inferred", {})
    pages = summary.get("pages", [])
    page_lines = [
        f"Pagina {p['page']}: {p.get('description') or 'sem descricao'}; "
        f"texto={p['text_chars']}; critica={p['is_critical']}"
        for p in pages
    ]
    header = "\n".join(
        [
            f"Arquivo: {summary.get('file_name', '')}",
            f"Paginas: {summary.get('pages_count', 0)}",
            f"Cliente inferido: {metadata.get('cliente') or 'nao identificado'}",
            f"Documento inferido: {metadata.get('documento') or 'nao identificado'}",
            f"Pedido inferido: {metadata.get('pedido') or 'nao identificado'}",
            f"Projeto inferido: {metadata.get('projeto') or 'nao identificado'}",
            "",
            "Mapa de paginas:",
            "\n".join(page_lines),
            "",
            "Texto extraido do PDF:",
        ]
    )
    remaining = max(0, max_chars - len(header))
    return f"{header}\n{summary.get('text', '')[:remaining]}"


def _first_match(value: str, pattern: str) -> str:
    match = re.search(pattern, value or "")
    return match.group(0).strip() if match else ""
