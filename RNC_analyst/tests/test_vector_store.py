from __future__ import annotations

import math
import unittest

from src.vector_store import (
    coerce_huggingface_embeddings,
    coerce_single_embedding,
    hashing_embedding,
    normalize_huggingface_url,
    normalize_provider,
    sanitize_collection_name,
)


class VectorStoreTests(unittest.TestCase):
    def test_hashing_embedding_is_stable_and_normalized(self) -> None:
        text = "layout painel borne cabo identificacao componente"

        first = hashing_embedding(text, dimensions=32)
        second = hashing_embedding(text, dimensions=32)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 32)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in first)), 1.0)

    def test_hashing_embedding_handles_empty_text(self) -> None:
        self.assertEqual(hashing_embedding("", dimensions=8), [0.0] * 8)

    def test_huggingface_response_with_token_vectors_is_mean_pooled(self) -> None:
        payload = [
            [[1.0, 0.0], [0.0, 1.0]],
            [[2.0, 0.0], [0.0, 2.0]],
        ]

        vectors = coerce_huggingface_embeddings(payload, expected_count=2)

        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 2)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in vectors[0])), 1.0)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in vectors[1])), 1.0)

    def test_provider_aliases_and_collection_names_are_safe(self) -> None:
        self.assertEqual(normalize_provider("hugging-face"), "huggingface")
        self.assertEqual(normalize_provider("off"), "disabled")
        self.assertEqual(normalize_provider("desconhecido"), "local_hash")
        self.assertEqual(sanitize_collection_name(" rnc casos cliente/linha "), "rnc_casos_cliente_linha")

    def test_coerces_numpy_like_embeddings(self) -> None:
        class NumpyLike:
            def tolist(self) -> list[float]:
                return [0.2, 0.3, 0.5]

        self.assertEqual(coerce_single_embedding(NumpyLike()), [0.2, 0.3, 0.5])

    def test_deprecated_huggingface_url_is_ignored(self) -> None:
        self.assertEqual(
            normalize_huggingface_url(
                "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
            ),
            "",
        )
        self.assertEqual(normalize_huggingface_url("https://example.com/embed"), "https://example.com/embed")


if __name__ == "__main__":
    unittest.main()
