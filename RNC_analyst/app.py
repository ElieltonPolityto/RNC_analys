from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.analysis import analyze_project
from src.database import init_db, list_analyses, save_analysis
from src.pdf_tools import ensure_runtime_dirs, parse_pdf_bytes, save_uploaded_pdf
from src.report_writer import write_reports


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIRS = ensure_runtime_dirs(BASE_DIR)
DB_PATH = RUNTIME_DIRS["data"] / "rnc_analyst.db"


DEFAULT_MODELS = {
    "Pre-analise local": "local",
    "OpenAI": "gpt-5.4-mini",
    "Anthropic": "claude-sonnet-4-20250514",
    "Groq": "meta-llama/llama-4-scout-17b-16e-instruct",
}


API_ENV = {
    "OpenAI": "OPENAI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "Groq": "GROQ_API_KEY",
}


MODEL_ENV = {
    "OpenAI": "OPENAI_MODEL",
    "Anthropic": "ANTHROPIC_MODEL",
    "Groq": "GROQ_MODEL",
}


@st.cache_data(show_spinner=False)
def cached_parse_pdf(file_bytes: bytes, file_name: str) -> dict[str, Any]:
    return parse_pdf_bytes(file_bytes, file_name)


def main() -> None:
    load_dotenv(BASE_DIR / ".env")
    init_db(DB_PATH)

    st.set_page_config(page_title="RNC Analyst", layout="wide")
    st.title("RNC Analyst")
    st.caption("Revisao preventiva de projetos eletricos antes do envio para producao.")

    provider, model, api_key = render_sidebar()
    tab_new, tab_history, tab_settings = st.tabs(["Nova analise", "Historico", "Configuracoes"])

    with tab_new:
        render_new_analysis(provider, model, api_key)
    with tab_history:
        render_history()
    with tab_settings:
        render_settings()


def render_sidebar() -> tuple[str, str, str]:
    st.sidebar.header("Analise")
    provider = st.sidebar.selectbox(
        "Provedor",
        ["Pre-analise local", "OpenAI", "Anthropic", "Groq"],
        help="Sem chave de API, o app executa apenas a pre-analise local.",
    )

    default_model = os.getenv(MODEL_ENV.get(provider, ""), DEFAULT_MODELS[provider])
    model = st.sidebar.text_input("Modelo", value=default_model)

    api_key = ""
    if provider != "Pre-analise local":
        env_name = API_ENV[provider]
        env_value = os.getenv(env_name, "")
        typed_key = st.sidebar.text_input(
            f"Chave {provider}",
            type="password",
            placeholder=f"Opcional se {env_name} estiver no .env",
        )
        api_key = typed_key or env_value
        if not api_key:
            st.sidebar.warning("Chave nao configurada. A analise sera local.")

    st.sidebar.divider()
    st.sidebar.caption("PDFs, uploads, relatorios, banco local e .env nao sao enviados ao Git.")
    return provider, model, api_key


def render_new_analysis(provider: str, model: str, api_key: str) -> None:
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
        result = analyze_project(
            provider=provider,
            api_key=api_key,
            model=model,
            pdf_bytes=file_bytes,
            file_name=uploaded_file.name,
            pdf_summary=pdf_summary,
            project_info=project_info,
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

    findings = pd.DataFrame(result.get("findings", []))
    if findings.empty:
        st.info("Nenhum apontamento registrado.")
    else:
        st.subheader("Apontamentos")
        st.dataframe(findings, use_container_width=True, hide_index=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.download_button(
            "Baixar Excel",
            data=report_paths["xlsx"].read_bytes(),
            file_name=report_paths["xlsx"].name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_b:
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


def render_settings() -> None:
    st.subheader("Arquivos locais")
    st.code(
        "\n".join(
            [
                f"Banco SQLite: {DB_PATH}",
                f"Uploads: {RUNTIME_DIRS['uploads']}",
                f"Relatorios: {RUNTIME_DIRS['reports']}",
                f"Exemplo de ambiente: {BASE_DIR / '.env.example'}",
            ]
        )
    )
    st.subheader("Chaves de API")
    st.write("Crie um arquivo .env ao lado do app.py usando .env.example como base.")
    st.write("As chaves nunca sao gravadas no banco nem exportadas para relatorios.")
    st.subheader("Modo Groq")
    st.write(
        "Neste MVP, Groq usa o texto extraido do PDF. A analise visual por paginas convertidas "
        "em imagem entra na proxima etapa."
    )


def build_record(
    *,
    project_info: dict[str, str],
    result: dict[str, Any],
    pdf_summary: dict[str, Any],
    pdf_name: str,
    upload_path: Path,
    report_paths: dict[str, Path],
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

