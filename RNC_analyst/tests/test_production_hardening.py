from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from src.ai_providers.openai_provider import is_transient_provider_error
from src.analysis import coerce_confidence, humanize_provider_error, max_severity, normalize_finding
from src.pdf_tools import parse_pdf_bytes, save_uploaded_pdf
from src.report_writer import write_markdown


class ProductionHardeningTests(unittest.TestCase):
    def test_saved_uploads_do_not_collide_with_same_original_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            uploads_dir = Path(tmp)

            first = save_uploaded_pdf(b"first", "../../Projeto Principal.pdf", uploads_dir)
            second = save_uploaded_pdf(b"second", "../../Projeto Principal.pdf", uploads_dir)

            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b"first")
            self.assertEqual(second.read_bytes(), b"second")
            self.assertTrue(first.name.endswith("_Projeto_Principal.pdf"))

    def test_invalid_pdf_raises_user_friendly_error(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaisesRegex(ValueError, "Nao foi possivel abrir o PDF"):
                parse_pdf_bytes(b"isto nao e um pdf", "quebrado.pdf")

    def test_markdown_keeps_related_cases_outside_findings_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "relatorio.md"
            write_markdown(
                path,
                project_info={"usuario": "Ana", "cliente": "ACME"},
                result={
                    "generated_at": "2026-05-04T10:00:00",
                    "provider": "Modelo local",
                    "model": "local",
                    "status": "concluido",
                    "overall_risk": "medio",
                    "related_cases_count": 1,
                    "summary": "Resumo executivo.",
                    "related_cases": [
                        {
                            "case_id": "ID01",
                            "retrieval_method": "lexical",
                            "similarity": "media",
                            "score": 0.42,
                        }
                    ],
                    "findings": [
                        {
                            "severity": "media",
                            "category": "Layout",
                            "page": 3,
                            "confidence": 0.8,
                            "source": "triagem_local",
                            "evidence": "Evidencia.",
                            "recommendation": "Revisar.",
                        }
                    ],
                },
                pdf_summary={"pages_count": 1, "inferred": {}, "critical_pages": [], "warnings": []},
            )

            text = path.read_text(encoding="utf-8")
            self.assertLess(text.index("## Casos historicos relacionados"), text.index("## Apontamentos"))
            self.assertGreater(text.index("### 1. Layout"), text.index("## Apontamentos"))

    def test_provider_findings_are_normalized_before_report_generation(self) -> None:
        finding = normalize_finding(
            {"severity": "média", "confidence": "1.7", "category": "Teste"},
            "ia",
        )

        self.assertEqual(finding["severity"], "media")
        self.assertEqual(finding["confidence"], 1.0)
        self.assertEqual(coerce_confidence("nao numerico", default=0.4), 0.4)
        self.assertEqual(max_severity([{"severity": "baixo"}, {"severity": "Alta"}]), "alta")

    def test_openai_520_error_is_retried_and_made_readable(self) -> None:
        html_error = Exception(
            "<html><title>api.openai.com | 520: Web server is returning an unknown error</title></html>"
        )

        message = humanize_provider_error(html_error, "OpenAI", "gpt-5")

        self.assertTrue(is_transient_provider_error(html_error))
        self.assertIn("erro temporario 520", message)
        self.assertIn("pre-analise local", message)
        self.assertNotIn("<html>", message)


if __name__ == "__main__":
    unittest.main()
