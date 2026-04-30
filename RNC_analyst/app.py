from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.analysis import analyze_project
from src.case_base import (
    ensure_case_base,
    fingerprint_case_base,
    index_all_cases,
    init_case_tables,
    list_case_dirs,
    list_indexed_cases,
    load_base_instructions,
    prompt_hash,
    save_base_instructions,
    search_similar_cases,
)
from src.database import init_db, list_analyses, save_analysis
from src.pdf_tools import ensure_runtime_dirs, parse_pdf_bytes, save_uploaded_pdf
from src.report_writer import write_reports
from src.vector_store import load_vector_config


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIRS = ensure_runtime_dirs(BASE_DIR)
CASE_BASE_PATHS = ensure_case_base(BASE_DIR)
DB_PATH = RUNTIME_DIRS["data"] / "rnc_analyst.db"


DEFAULT_MODELS = {
    "Modelo local": "local",
    "OpenAI": "gpt-5.5",
}


API_ENV = {
    "OpenAI": "OPENAI_API_KEY",
}


MODEL_ENV = {
    "OpenAI": "OPENAI_MODEL",
}


@st.cache_data(show_spinner=False)
def cached_parse_pdf(file_bytes: bytes, file_name: str) -> dict[str, Any]:
    return parse_pdf_bytes(file_bytes, file_name)


def main() -> None:
    load_dotenv(BASE_DIR / ".env", override=True)
    init_db(DB_PATH)
    init_case_tables(DB_PATH)
    autoindex_result = autoindex_case_base()

    st.set_page_config(page_title="RNC Analyst", layout="wide")
    st.title("RNC Analyst")
    st.caption("Revisao preventiva de projetos eletricos antes do envio para producao.")
    render_autoindex_status(autoindex_result)

    provider, model, api_key, case_limit = render_sidebar()
    tab_new, tab_case_base, tab_prompt, tab_history, tab_settings = st.tabs(
        ["Nova analise", "Base RNC", "Prompt", "Historico", "Configuracoes"]
    )

    with tab_new:
        render_new_analysis(provider, model, api_key, case_limit)
    with tab_case_base:
        render_case_base()
    with tab_prompt:
        render_prompt_editor()
    with tab_history:
        render_history()
    with tab_settings:
        render_settings()


def autoindex_case_base() -> dict[str, Any]:
    knowledge_base = CASE_BASE_PATHS["knowledge_base"]
    signature = case_base_runtime_signature(knowledge_base)
    last_signature = st.session_state.get("case_base_signature")
    if last_signature == signature:
        return {
            "ran": False,
            "reason": "sem_alteracao",
            "signature": signature,
            "result": st.session_state.get("case_base_last_index_result"),
        }

    result = index_all_cases(DB_PATH, knowledge_base, RUNTIME_DIRS["vectors"])
    st.session_state["case_base_signature"] = signature
    st.session_state["case_base_last_index_result"] = result
    return {"ran": True, "reason": "base_alterada", "signature": signature, "result": result}


def case_base_runtime_signature(knowledge_base: Path) -> str:
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


def render_autoindex_status(autoindex_result: dict[str, Any]) -> None:
    result = autoindex_result.get("result") or {}
    if autoindex_result.get("ran"):
        vector_index = result.get("vector_index") or {}
        vector_message = vector_index.get("message") or "Busca vetorial nao executada."
        st.caption(
            "Base RNC indexada automaticamente: "
            f"{result.get('ok', 0)} ok, {result.get('warning', 0)} alerta, "
            f"{result.get('error', 0)} erro, {result.get('pruned', 0)} removido. "
            f"{vector_message}"
        )


def render_sidebar() -> tuple[str, str, str, int]:
    st.sidebar.header("Analise")
    provider = st.sidebar.selectbox(
        "Provedor",
        ["OpenAI", "Modelo local"],
        help="A chave da OpenAI fica somente no arquivo .env.",
    )

    default_model = normalize_model_id(os.getenv(MODEL_ENV.get(provider, ""), DEFAULT_MODELS[provider]))
    model = default_model

    api_key = ""
    if provider == "OpenAI":
        api_key = os.getenv(API_ENV[provider], "")
        if not api_key:
            st.sidebar.warning("OPENAI_API_KEY nao configurada no .env. A analise sera local.")

    st.sidebar.divider()
    case_limit = st.sidebar.slider(
        "Casos historicos",
        min_value=0,
        max_value=8,
        value=5,
        help="Quantidade maxima de casos similares anexados ao prompt.",
    )
    st.sidebar.divider()
    st.sidebar.caption("Chaves de API ficam apenas no .env. PDFs, relatorios e base local nao vao ao Git.")
    return provider, model, api_key, case_limit


def normalize_model_id(value: str) -> str:
    model = (value or "").strip()
    model = re.sub(r"[\s_]+", "-", model)
    return model or DEFAULT_MODELS["OpenAI"]


def render_new_analysis(provider: str, model: str, api_key: str, case_limit: int) -> None:
    uploaded_file = st.file_uploader("Arquivo PDF do projeto", type=["pdf"])
    if not uploaded_file:
        st.info("Envie um PDF para iniciar a revisao preventiva.")
        return

    file_bytes = uploaded_file.getvalue()
    with st.spinner("Lendo PDF e extraindo metadados..."):
        pdf_summary = cached_parse_pdf(file_bytes, uploaded_file.name)

    inferred = pdf_summary.get("inferred", {})
    render_pdf_overview(pdf_summary)

    with st.form("analysis_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            user_name = st.text_input("Usuario", value=os.getenv("USERNAME", ""))
            customer = st.text_input("Cliente", value=inferred.get("cliente", ""))
        with col2:
            document = st.text_input("Documento", value=inferred.get("documento", ""))
            order = st.text_input("Pedido", value=inferred.get("pedido", ""))
        with col3:
            project = st.text_input("Projeto", value=inferred.get("projeto", ""))
            revision = st.text_input("Revisao", value=inferred.get("revisao", ""))

        submitted = st.form_submit_button("Analisar projeto", use_container_width=True)

    if not submitted:
        return

    project_info = {
        "usuario": user_name.strip(),
        "cliente": customer.strip(),
        "documento": document.strip(),
        "pedido": order.strip(),
        "projeto": project.strip(),
        "revisao": revision.strip(),
    }

    if not project_info["usuario"]:
        st.error("Informe o usuario que esta gerando o relatorio.")
        return

    with st.spinner("Executando analise..."):
        upload_path = save_uploaded_pdf(file_bytes, uploaded_file.name, RUNTIME_DIRS["uploads"])
        base_instructions = load_base_instructions(CASE_BASE_PATHS["instructions"])
        similar_cases = search_similar_cases(
            DB_PATH,
            pdf_summary=pdf_summary,
            project_info=project_info,
            limit=case_limit,
            vector_dir=RUNTIME_DIRS["vectors"],
        )
        result = analyze_project(
            provider=provider,
            api_key=api_key,
            model=model,
            pdf_bytes=file_bytes,
            file_name=uploaded_file.name,
            pdf_summary=pdf_summary,
            project_info=project_info,
            base_instructions=base_instructions,
            similar_cases=similar_cases,
        )
        report_paths = write_reports(
            reports_dir=RUNTIME_DIRS["reports"],
            project_info=project_info,
            result=result,
            pdf_summary=pdf_summary,
            original_file_name=uploaded_file.name,
        )
        record = build_record(
            project_info=project_info,
            result=result,
            pdf_summary=pdf_summary,
            pdf_name=uploaded_file.name,
            upload_path=upload_path,
            report_paths=report_paths,
            related_cases=similar_cases,
            base_prompt=base_instructions,
        )
        analysis_id = save_analysis(DB_PATH, record)

    st.success(f"Analise registrada com ID {analysis_id}.")
    render_result(result, report_paths)


def render_pdf_overview(pdf_summary: dict[str, Any]) -> None:
    inferred = pdf_summary.get("inferred", {})
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Paginas", pdf_summary.get("pages_count", 0))
    col2.metric("Paginas criticas", len(pdf_summary.get("critical_pages", [])))
    col3.metric("Documento", inferred.get("documento") or "-")
    col4.metric("Projeto", inferred.get("projeto") or "-")

    if pdf_summary.get("warnings"):
        st.warning("O PDF foi lido com avisos. Se houver falha na analise, reexporte ou normalize o arquivo.")

    with st.expander("Mapa de paginas"):
        pages_df = pd.DataFrame(pdf_summary.get("pages", []))
        if not pages_df.empty:
            st.dataframe(
                pages_df[
                    [
                        "page",
                        "description",
                        "text_chars",
                        "is_text_sparse",
                        "is_critical",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )


def render_result(result: dict[str, Any], report_paths: dict[str, Path]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status", result.get("status", ""))
    col2.metric("Risco geral", result.get("overall_risk", ""))
    col3.metric("Apontamentos", result.get("findings_count", 0))
    col4.metric("Severidade maxima", result.get("max_severity", ""))

    if result.get("provider_error"):
        st.warning(result["provider_error"])

    st.subheader("Resumo")
    st.write(result.get("summary", ""))

    related_cases = pd.DataFrame(result.get("related_cases", []))
    if not related_cases.empty:
        st.subheader("Casos historicos relacionados")
        visible_columns = [
            "case_id",
            "retrieval_method",
            "similarity",
            "score",
            "vector_score",
            "rnc_type",
            "severity",
            "root_cause",
            "preventive_action",
        ]
        existing_columns = [column for column in visible_columns if column in related_cases.columns]
        st.dataframe(related_cases[existing_columns], use_container_width=True, hide_index=True)

    findings = pd.DataFrame(result.get("findings", []))
    if findings.empty:
        st.info("Nenhum apontamento registrado.")
    else:
        st.subheader("Apontamentos")
        st.dataframe(findings, use_container_width=True, hide_index=True)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.download_button(
            "Baixar PDF",
            data=report_paths["pdf"].read_bytes(),
            file_name=report_paths["pdf"].name,
            mime="application/pdf",
            use_container_width=True,
        )
    with col_b:
        st.download_button(
            "Baixar Excel",
            data=report_paths["xlsx"].read_bytes(),
            file_name=report_paths["xlsx"].name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_c:
        st.download_button(
            "Baixar Markdown",
            data=report_paths["md"].read_text(encoding="utf-8"),
            file_name=report_paths["md"].name,
            mime="text/markdown",
            use_container_width=True,
        )


def render_history() -> None:
    rows = list_analyses(DB_PATH)
    if not rows:
        st.info("Nenhuma analise registrada ainda.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_case_base() -> None:
    knowledge_base = CASE_BASE_PATHS["knowledge_base"]
    indexed_cases = list_indexed_cases(DB_PATH)
    case_dirs = list_case_dirs(knowledge_base)
    vector_config = load_vector_config()
    last_index = st.session_state.get("case_base_last_index_result") or {}
    vector_index = last_index.get("vector_index") or {}

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pastas ID", len(case_dirs))
    col2.metric("Casos indexados", len(indexed_cases))
    col3.metric("Base local", knowledge_base.name)
    col4.metric("Busca vetorial", vector_index.get("state") or "pendente")

    st.code(str(knowledge_base))
    st.info("A base e indexada automaticamente quando o app abre ou quando a pasta knowledge_base muda.")
    st.caption(
        f"ChromaDB: {RUNTIME_DIRS['vectors']} | "
        f"Provedor de embedding: {vector_config.provider} | Colecao: {vector_config.collection}"
    )

    if st.button("Reindexar base agora", type="primary", use_container_width=True):
        with st.spinner("Indexando casos historicos..."):
            result = index_all_cases(DB_PATH, knowledge_base, RUNTIME_DIRS["vectors"])
            st.session_state["case_base_signature"] = case_base_runtime_signature(knowledge_base)
            st.session_state["case_base_last_index_result"] = result
        st.success(
            f"Indexacao concluida: {result['ok']} ok, {result['warning']} alerta, {result['error']} erro."
        )
        st.json(result)

    st.subheader("Casos encontrados")
    if case_dirs:
        st.dataframe(
            pd.DataFrame({"case_id": [path.name for path in case_dirs], "pasta": [str(path) for path in case_dirs]}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhuma pasta ID encontrada ainda.")

    st.subheader("Indice atual")
    if indexed_cases:
        df = pd.DataFrame(indexed_cases)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum caso indexado ainda.")


def render_prompt_editor() -> None:
    instructions_path = CASE_BASE_PATHS["instructions"]
    current = load_base_instructions(instructions_path)

    col1, col2 = st.columns(2)
    col1.metric("Hash atual", prompt_hash(current))
    col2.metric("Arquivo", instructions_path.name)
    st.code(str(instructions_path))

    edited = st.text_area("Instrucoes base", value=current, height=420)
    if st.button("Salvar prompt", type="primary", use_container_width=True):
        save_base_instructions(instructions_path, edited)
        st.success(f"Prompt salvo. Hash: {prompt_hash(edited)}")


def render_settings() -> None:
    st.subheader("Arquivos locais")
    st.code(
        "\n".join(
            [
                f"Banco SQLite: {DB_PATH}",
                f"Uploads: {RUNTIME_DIRS['uploads']}",
                f"Relatorios: {RUNTIME_DIRS['reports']}",
                f"ChromaDB: {RUNTIME_DIRS['vectors']}",
                f"Base RNC: {CASE_BASE_PATHS['knowledge_base']}",
                f"Prompt base: {CASE_BASE_PATHS['instructions']}",
                f"Exemplo de ambiente: {BASE_DIR / '.env.example'}",
            ]
        )
    )
    st.subheader("Chaves de API")
    st.write("Crie um arquivo .env ao lado do app.py usando .env.example como base.")
    st.write("As chaves nunca sao gravadas no banco nem exportadas para relatorios.")


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
        "base_prompt_path": str(CASE_BASE_PATHS["instructions"]),
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


if __name__ == "__main__":
    main()
