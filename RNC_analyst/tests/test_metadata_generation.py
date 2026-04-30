from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from src.case_base import generate_metadata_files


class MetadataGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("tests") / "_tmp_metadata"
        if self.root.exists():
            shutil.rmtree(self.root)
        self.knowledge_base = self.root / "knowledge_base"
        self.knowledge_base.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_creates_metadata_from_case_text_files(self) -> None:
        case_dir = self.knowledge_base / "ID01"
        case_dir.mkdir()
        (case_dir / "projeto_QPL1.txt").write_text(
            "\n".join(
                [
                    "Cliente: ACME INDUSTRIAL",
                    "Documento: R24YV044A.03",
                    "Pedido: 241084",
                    "Projeto: QPL1",
                    "REV. A",
                ]
            ),
            encoding="utf-8",
        )
        (case_dir / "rnc_layout.txt").write_text(
            "\n".join(
                [
                    "Tipo: Layout",
                    "Data da ocorrencia: 10/01/2026",
                    "Causa raiz: Falta de cota na porta",
                    "Acao corretiva: Atualizar layout",
                    "Pagina 12",
                    "Tags: KM1 QF2",
                ]
            ),
            encoding="utf-8",
        )

        result = generate_metadata_files(self.knowledge_base)

        metadata = json.loads((case_dir / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(result["created"], 1)
        self.assertEqual(metadata["case_id"], "ID01")
        self.assertEqual(metadata["cliente"], "ACME INDUSTRIAL")
        self.assertEqual(metadata["documento"], "R24YV044A.03")
        self.assertEqual(metadata["pedido"], "241084")
        self.assertEqual(metadata["projeto"], "QPL1")
        self.assertIn("Layout", metadata["tipo_rnc"])
        self.assertIn(12, metadata["paginas_relacionadas"])
        self.assertIn("KM1", metadata["tags_componentes"])

    def test_fills_only_empty_fields_in_existing_metadata(self) -> None:
        case_dir = self.knowledge_base / "ID02"
        case_dir.mkdir()
        (case_dir / "projeto_QPL2.txt").write_text(
            "Cliente: CLIENTE INFERIDO\nDocumento: R24YV044A.04\nProjeto: QPL2\n",
            encoding="utf-8",
        )
        (case_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "case_id": "ID02",
                    "cliente": "CLIENTE MANUAL",
                    "documento": "",
                    "projeto": "",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = generate_metadata_files(self.knowledge_base, fill_existing_empty=True)

        metadata = json.loads((case_dir / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(result["updated"], 1)
        self.assertEqual(metadata["cliente"], "CLIENTE MANUAL")
        self.assertEqual(metadata["documento"], "R24YV044A.04")
        self.assertEqual(metadata["projeto"], "QPL2")


if __name__ == "__main__":
    unittest.main()
