from __future__ import annotations

import hashlib
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_LOCAL_DIMENSIONS = 384
DEFAULT_HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True)
class VectorConfig:
    provider: str
    collection: str
    local_dimensions: int
    huggingface_model: str
    huggingface_url: str
    huggingface_token: str


def load_vector_config() -> VectorConfig:
    provider = normalize_provider(os.getenv("EMBEDDING_PROVIDER", "local_hash"))
    local_dimensions = parse_positive_int(os.getenv("LOCAL_EMBEDDING_DIMENSIONS"), DEFAULT_LOCAL_DIMENSIONS)
    hf_model = os.getenv("HUGGINGFACE_EMBEDDING_MODEL", DEFAULT_HF_MODEL).strip() or DEFAULT_HF_MODEL
    hf_url = normalize_huggingface_url(os.getenv("HUGGINGFACE_EMBEDDING_URL", ""))
    hf_token = (
        os.getenv("HUGGINGFACE_API_TOKEN", "").strip()
        or os.getenv("HF_TOKEN", "").strip()
    )
    collection = os.getenv("CHROMA_COLLECTION", "").strip()
    if not collection:
        collection = default_collection_name(provider, hf_model, local_dimensions)

    return VectorConfig(
        provider=provider,
        collection=sanitize_collection_name(collection),
        local_dimensions=local_dimensions,
        huggingface_model=hf_model,
        huggingface_url=hf_url,
        huggingface_token=hf_token,
    )


def normalize_provider(value: str) -> str:
    provider = (value or "").strip().lower().replace("-", "_")
    if provider in {"hf", "hugging_face"}:
        return "huggingface"
    if provider in {"off", "none", "disabled", "desativado"}:
        return "disabled"
    if provider not in {"local_hash", "huggingface", "disabled"}:
        return "local_hash"
    return provider


def normalize_huggingface_url(value: str) -> str:
    url = (value or "").strip()
    if not url:
        return ""
    if "api-inference.huggingface.co/pipeline/feature-extraction" in url:
        return ""
    return url


def default_collection_name(provider: str, hf_model: str, local_dimensions: int) -> str:
    if provider == "huggingface":
        digest = hashlib.sha1(hf_model.encode("utf-8")).hexdigest()[:8]
        return f"rnc_cases_hf_{digest}"
    if provider == "disabled":
        return "rnc_cases_disabled"
    return f"rnc_cases_local_{local_dimensions}"


def sanitize_collection_name(value: str) -> str:
    # Chroma requires 3-63 chars, alphanumeric start/end, and only dots, underscores or hyphens.
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if len(name) < 3:
        name = f"rnc_{name or 'cases'}"
    if len(name) > 63:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
        name = f"{name[:54].rstrip('._-')}_{digest}"
    return name


def parse_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or "")
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def sync_vector_index(chroma_dir: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    config = load_vector_config()
    status = base_status(config)
    if config.provider == "disabled":
        status.update({"state": "disabled", "message": "Busca vetorial desativada por configuracao."})
        return status

    try:
        chromadb = import_chromadb()
        chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(chroma_dir))
        recreate_collection(client, config.collection)
        collection = client.get_or_create_collection(
            name=config.collection,
            metadata={"hnsw:space": "cosine"},
        )

        prepared = [prepare_vector_record(record) for record in records]
        prepared = [record for record in prepared if record["document"].strip()]
        for batch in batched(prepared, 16):
            documents = [item["document"] for item in batch]
            embeddings = embed_texts(documents, config)
            collection.upsert(
                ids=[item["id"] for item in batch],
                documents=documents,
                metadatas=[item["metadata"] for item in batch],
                embeddings=embeddings,
            )

        status.update(
            {
                "state": "ready",
                "enabled": True,
                "count": len(prepared),
                "message": f"Indice vetorial atualizado com {len(prepared)} caso(s).",
            }
        )
        return status
    except Exception as exc:
        status.update(
            {
                "state": "unavailable",
                "message": f"Busca vetorial indisponivel; fallback lexical ativo. Detalhe: {exc}",
            }
        )
        return status


def query_vector_cases(chroma_dir: Path, query_text: str, limit: int) -> dict[str, Any]:
    config = load_vector_config()
    status = base_status(config)
    if config.provider == "disabled":
        status.update({"state": "disabled", "message": "Busca vetorial desativada por configuracao."})
        return {"status": status, "matches": []}

    if limit <= 0 or not query_text.strip():
        status.update({"state": "empty_query", "message": "Consulta vazia."})
        return {"status": status, "matches": []}

    try:
        chromadb = import_chromadb()
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(name=config.collection)
        if collection.count() == 0:
            status.update({"state": "empty", "message": "Indice vetorial sem casos."})
            return {"status": status, "matches": []}

        embedding = embed_texts([query_text], config)[0]
        raw = collection.query(
            query_embeddings=[embedding],
            n_results=max(1, limit),
            include=["distances", "metadatas"],
        )
        matches = normalize_query_result(raw)
        status.update(
            {
                "state": "ready",
                "enabled": True,
                "count": collection.count(),
                "message": f"{len(matches)} caso(s) recuperado(s) por similaridade vetorial.",
            }
        )
        return {"status": status, "matches": matches}
    except Exception as exc:
        status.update(
            {
                "state": "unavailable",
                "message": f"Busca vetorial indisponivel; fallback lexical ativo. Detalhe: {exc}",
            }
        )
        return {"status": status, "matches": []}


def base_status(config: VectorConfig) -> dict[str, Any]:
    return {
        "enabled": False,
        "state": "unknown",
        "provider": config.provider,
        "collection": config.collection,
        "count": 0,
        "message": "",
    }


def import_chromadb() -> Any:
    try:
        import chromadb  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("instale a dependencia chromadb ou execute o .bat novamente") from exc
    return chromadb


def recreate_collection(client: Any, collection_name: str) -> None:
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass


def prepare_vector_record(record: dict[str, Any]) -> dict[str, Any]:
    case_id = str(record.get("case_id") or "").strip()
    summary = str(record.get("summary_text") or "")
    search = str(record.get("search_text") or "")
    document = "\n".join(
        [
            f"Caso: {case_id}",
            f"Titulo: {record.get('title') or ''}",
            f"Cliente: {record.get('customer') or ''}",
            f"Documento: {record.get('document') or ''}",
            f"Projeto: {record.get('project') or ''}",
            f"Tipo de RNC: {record.get('rnc_type') or ''}",
            f"Severidade: {record.get('severity') or ''}",
            f"Causa raiz: {record.get('root_cause') or ''}",
            f"Acao preventiva: {record.get('preventive_action') or ''}",
            "",
            summary[:10000],
            "",
            search[:6000],
        ]
    )
    return {
        "id": case_id,
        "document": document[:18000],
        "metadata": compact_metadata(record),
    }


def compact_metadata(record: dict[str, Any]) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {}
    for key in [
        "case_id",
        "status",
        "title",
        "customer",
        "document",
        "project",
        "revision",
        "rnc_type",
        "severity",
        "root_cause",
        "preventive_action",
        "file_fingerprint",
    ]:
        value = record.get(key)
        metadata[key] = "" if value is None else str(value)[:1000]
    return metadata


def embed_texts(texts: list[str], config: VectorConfig) -> list[list[float]]:
    if config.provider == "huggingface":
        return embed_with_huggingface(texts, config)
    return [hashing_embedding(text, config.local_dimensions) for text in texts]


def embed_with_huggingface(texts: list[str], config: VectorConfig) -> list[list[float]]:
    if not config.huggingface_token:
        raise RuntimeError("HUGGINGFACE_API_TOKEN nao configurado no .env")

    if not texts:
        return []

    if not config.huggingface_url:
        try:
            return embed_with_huggingface_client(texts, config)
        except Exception as exc:
            raise RuntimeError(
                "Falha no Hugging Face InferenceClient. "
                "Confira token, permissoes de Inference Providers e modelo configurado. "
                f"Detalhe: {exc}"
            ) from exc

    return embed_with_huggingface_url(texts, config)


def embed_with_huggingface_client(texts: list[str], config: VectorConfig) -> list[list[float]]:
    try:
        from huggingface_hub import InferenceClient  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("instale a dependencia huggingface-hub ou execute o .bat novamente") from exc

    client = InferenceClient(
        model=config.huggingface_model,
        provider="hf-inference",
        token=config.huggingface_token,
        timeout=90,
    )
    embeddings = [
        client.feature_extraction(
            text,
            normalize=True,
            truncate=True,
        )
        for text in texts
    ]
    return [coerce_single_embedding(embedding) for embedding in embeddings]


def embed_with_huggingface_url(texts: list[str], config: VectorConfig) -> list[list[float]]:
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("instale a dependencia requests ou execute o .bat novamente") from exc

    response = requests.post(
        config.huggingface_url,
        headers={"Authorization": f"Bearer {config.huggingface_token}"},
        json={"inputs": texts, "normalize": True, "truncate": True},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    return coerce_huggingface_embeddings(payload, len(texts))


def hashing_embedding(text: str, dimensions: int = DEFAULT_LOCAL_DIMENSIONS) -> list[float]:
    tokens = tokenize_for_embedding(text)
    if not tokens:
        return [0.0] * dimensions

    terms = tokens + [f"{tokens[index]}_{tokens[index + 1]}" for index in range(len(tokens) - 1)]
    vector = [0.0] * dimensions
    for term in terms:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 else -1.0
        weight = 1.0 + min(len(term), 24) / 24.0
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def tokenize_for_embedding(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9][a-z0-9_.-]{2,}", normalized)


def coerce_huggingface_embeddings(payload: Any, expected_count: int) -> list[list[float]]:
    if isinstance(payload, dict):
        if "error" in payload:
            raise RuntimeError(str(payload["error"]))
        if "embeddings" in payload:
            payload = payload["embeddings"]

    if expected_count == 1:
        return [coerce_single_embedding(payload)]

    if isinstance(payload, list) and len(payload) == expected_count:
        return [coerce_single_embedding(item) for item in payload]

    raise RuntimeError("Resposta de embeddings do Hugging Face em formato inesperado.")


def coerce_single_embedding(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        return coerce_single_embedding(value.tolist())
    if is_number_list(value):
        return [float(item) for item in value]
    if isinstance(value, list) and value and all(is_number_list(item) for item in value):
        return mean_pool(value)
    if isinstance(value, list) and len(value) == 1:
        return coerce_single_embedding(value[0])
    raise RuntimeError("Embedding em formato inesperado.")


def is_number_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, (int, float)) for item in value)


def mean_pool(matrix: list[list[float]]) -> list[float]:
    width = len(matrix[0])
    totals = [0.0] * width
    rows = 0
    for row in matrix:
        if len(row) != width:
            continue
        rows += 1
        for index, value in enumerate(row):
            totals[index] += float(value)
    if rows == 0:
        raise RuntimeError("Embedding tokenizado vazio.")
    pooled = [value / rows for value in totals]
    norm = math.sqrt(sum(value * value for value in pooled))
    return [value / norm for value in pooled] if norm else pooled


def normalize_query_result(raw: dict[str, Any]) -> list[dict[str, Any]]:
    ids = (raw.get("ids") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    matches = []
    for index, case_id in enumerate(ids):
        distance = float(distances[index]) if index < len(distances) else 1.0
        metadata = metadatas[index] if index < len(metadatas) else {}
        matches.append(
            {
                "case_id": str(case_id),
                "vector_distance": round(distance, 6),
                "vector_score": round(max(0.0, min(1.0, 1.0 - distance)), 4),
                "metadata": metadata or {},
            }
        )
    return matches


def batched(items: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]
