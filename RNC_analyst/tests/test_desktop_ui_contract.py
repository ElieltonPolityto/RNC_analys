from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

from src import desktop_service
from src.report_writer import write_pdf


class DesktopUiContractTests(unittest.TestCase):
    def test_default_openai_model_is_economic(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(desktop_service.openai_model(), "gpt-5-mini")
            self.assertEqual(desktop_service.ai_mode_label(), "IA: economica")

    def test_project_info_does_not_require_manual_fields(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            project_info = desktop_service.build_project_info({})

        self.assertEqual(project_info["usuario"], "Usuario local")
        self.assertEqual(project_info["cliente"], "")
        self.assertEqual(project_info["documento"], "")
        self.assertEqual(project_info["pedido"], "")
        self.assertEqual(project_info["projeto"], "")
        self.assertEqual(project_info["revisao"], "")

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


if __name__ == "__main__":
    unittest.main()
