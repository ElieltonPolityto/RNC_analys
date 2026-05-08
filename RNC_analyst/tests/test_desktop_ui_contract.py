from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

from src import desktop_service
from src.prompts import build_review_prompt
from src.report_writer import write_pdf


class DesktopUiContractTests(unittest.TestCase):
    def test_default_openai_model_is_economic(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(desktop_service.openai_model(), "gpt-5-mini")
            self.assertEqual(desktop_service.ai_mode_label(), "IA economica: gpt-5-mini")

    def test_project_info_does_not_require_manual_fields(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            project_info = desktop_service.build_project_info({})

        self.assertEqual(project_info["usuario"], "Usuario local")
        self.assertEqual(project_info["cliente"], "")
        self.assertEqual(project_info["documento"], "")
        self.assertEqual(project_info["pedido"], "")
        self.assertEqual(project_info["projeto"], "")
        self.assertEqual(project_info["revisao"], "")

    def test_saves_openai_model_to_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            env_path = base_dir / ".env"
            env_path.write_text("OPENAI_API_KEY=abc\nOPENAI_MODEL=gpt-5-mini\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                saved = desktop_service.save_openai_model(base_dir, "gpt 5.2")
                self.assertEqual(os.environ["OPENAI_MODEL"], "gpt-5.2")

            self.assertEqual(saved, "gpt-5.2")
            self.assertIn("OPENAI_MODEL=gpt-5.2", env_path.read_text(encoding="utf-8"))

    def test_pdf_is_enxuto_and_operational(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "relatorio.pdf"
            write_pdf(
                path,
                project_info={"usuario": "Ana", "cliente": "", "documento": "2604108", "pedido": "123456"},
                result={
                    "generated_at": "2026-05-07T14:35:00",
                    "provider": "OpenAI",
                    "model": "gpt-5-mini",
                    "status": "concluido",
                    "overall_risk": "medio",
                    "findings_count": 1,
                    "max_severity": "media",
                    "related_cases_count": 2,
                    "summary": "Resumo curto da analise.",
                    "related_cases": [{"case_id": "ID03", "similarity": "alta"}],
                    "findings": [
                        {
                            "severity": "media",
                            "category": "Protecao do transformador TR1",
                            "page": 7,
                            "confidence": 0.9,
                            "source": "ia",
                            "evidence": "Fusivel secundario indicado como 4 A.",
                            "recommendation": "Ajustar o fusivel ou registrar justificativa tecnica.",
                        }
                    ],
                },
                pdf_summary={
                    "file_name": "projeto.pdf",
                    "pages_count": 21,
                    "inferred": {"cliente": "", "documento": "2604108", "pedido": "123456"},
                    "critical_pages": [7],
                    "warnings": [],
                },
            )

            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)

        self.assertIn("Arquivo", text)
        self.assertIn("Cliente", text)
        self.assertIn("Documento", text)
        self.assertIn("Resumo da analise", text)
        self.assertIn("Apontamentos para revisao", text)
        self.assertIn("Orientacao para producao", text)
        self.assertIn("Verificacao", text)
        self.assertIn("Acao", text)
        self.assertNotIn("Risco geral", text)
        self.assertNotIn("Severidade maxima", text)
        self.assertNotIn("Casos Historicos Relacionados", text)
        self.assertNotIn("ID03", text)
        self.assertNotIn("Confianca", text)
        self.assertNotIn("Fonte", text)
        self.assertNotIn("Pedido\n", text)
        self.assertNotIn("Projeto\n", text)
        self.assertNotIn("Revisao\n", text)
        self.assertNotIn("Usuario\n", text)
        self.assertNotIn("Gerado em\n", text)

    def test_prompt_uses_personas_and_ignores_historical_base(self) -> None:
        prompt = build_review_prompt(
            {"cliente": "", "documento": "R26CI011B.03"},
            "Material extraido.",
            base_instructions="Instrucao local.",
        )

        self.assertIn("Eletricista experiente de chao de fabrica", prompt)
        self.assertIn("Engenheiro eletricista senior", prompt)
        self.assertIn("43 paginas de comando", prompt)
        self.assertIn("CABO DE ALIMENTACAO E 4mm2", prompt)
        self.assertNotIn("Base historica de RNC", prompt)
        self.assertNotIn("cite o ID", prompt)

    def test_effective_prompt_preview_matches_analysis_prompt_contract(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            base_dir = Path(tmp)
            context = desktop_service.create_context(base_dir)
            desktop_service.save_prompt(context, "Instrucao local.")
            loaded = desktop_service.PdfLoadResult(
                path=base_dir / "R26CI011B.03-2604106-CXINTER.pdf",
                bytes_data=b"pdf",
                summary={
                    "file_name": "R26CI011B.03-2604106-CXINTER.pdf",
                    "pages_count": 1,
                    "inferred": {"cliente": "", "documento": "R26CI011B.03"},
                    "pages": [
                        {
                            "page": 1,
                            "description": "Lista de desenho",
                            "text_chars": 1200,
                            "is_critical": False,
                        }
                    ],
                    "critical_pages": [],
                    "warnings": [],
                    "text": "Material extraido.",
                },
            )

            prompt = desktop_service.build_effective_prompt(context, loaded)

        self.assertIn("=== SYSTEM INSTRUCTIONS ===", prompt)
        self.assertIn("=== USER PROMPT ===", prompt)
        self.assertIn("Eletricista experiente de chao de fabrica", prompt)
        self.assertIn("Engenheiro eletricista senior", prompt)
        self.assertIn("Instrucao local.", prompt)
        self.assertIn("R26CI011B.03", prompt)
        self.assertNotIn("Base historica de RNC", prompt)
        self.assertNotIn("cite o ID", prompt)

    def test_saved_base_prompt_has_no_old_historical_case_instructions(self) -> None:
        prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "instrucoes_base.txt"
        prompt = prompt_path.read_text(encoding="utf-8")

        self.assertIn("Ignorar histórico de RNC", prompt)
        self.assertIn("não apontar diferença entre folhas de comando e anexos/layouts", prompt)
        self.assertNotIn("O histórico de RNCs reais da empresa", prompt)
        self.assertNotIn("Comparar o projeto atual com casos históricos de RNC", prompt)
        self.assertNotIn("Citar o ID do caso histórico", prompt)
        self.assertNotIn("Caso histórico relacionado:", prompt)

    def test_desktop_analysis_progress_and_no_similar_cases(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            base_dir = Path(tmp)
            context = desktop_service.create_context(base_dir)
            pdf_path = base_dir / "projeto.pdf"
            pdf_path.write_bytes(b"pdf")
            loaded = desktop_service.PdfLoadResult(
                path=pdf_path,
                bytes_data=b"pdf",
                summary={
                    "file_name": "projeto.pdf",
                    "pages_count": 1,
                    "inferred": {},
                    "pages": [],
                    "critical_pages": [],
                    "warnings": [],
                },
            )
            progress_events: list[tuple[int, str]] = []

            with patch.dict(os.environ, {}, clear=True), patch(
                "src.desktop_service.analyze_project",
                return_value={
                    "generated_at": "2026-05-07T14:35:00",
                    "provider": "Modelo local",
                    "model": "local",
                    "status": "pre_analise_local",
                    "overall_risk": "baixo",
                    "findings": [],
                    "provider_error": "",
                    "related_cases": [],
                    "related_cases_count": 0,
                    "findings_count": 0,
                    "max_severity": "baixa",
                    "summary": "ok",
                },
            ) as mocked_analyze, patch(
                "src.desktop_service.write_reports",
                return_value={
                    "pdf": base_dir / "relatorio.pdf",
                    "xlsx": base_dir / "relatorio.xlsx",
                    "md": base_dir / "relatorio.md",
                },
            ):
                desktop_service.run_analysis(
                    context,
                    loaded,
                    progress=lambda percent, message: progress_events.append((percent, message)),
                )

        percents = [item[0] for item in progress_events]
        self.assertEqual(percents[0], 0)
        self.assertEqual(percents[-1], 100)
        self.assertEqual(percents, sorted(percents))
        self.assertEqual(mocked_analyze.call_args.kwargs["similar_cases"], [])

    def test_desktop_analysis_does_not_use_indeterminate_progress(self) -> None:
        desktop_app = Path(__file__).resolve().parents[1] / "desktop_app.py"
        self.assertNotIn("setRange(0, 0)", desktop_app.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
