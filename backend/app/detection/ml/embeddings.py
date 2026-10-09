import numpy as np

from app.config import get_settings
from app.core.logging import logger
from app.detection.context import ClaimData

DIM_FALLBACK = 256


def claim_text(claim: ClaimData, signal_names: list[str] | None = None) -> str:
    """Describes a claim by its codes and detected patterns. Contains no member identifiers."""
    parts = [
        f"type {claim.claim_type or 'unknown'}",
        "procedures " + " ".join(sorted(claim.cpt_codes)),
        "diagnoses " + " ".join(sorted(claim.diagnosis_codes)),
        f"billed band {int(np.log10(max(claim.total_billed or 1, 1)))}",
    ]
    if signal_names:
        parts.append("signals " + " ".join(sorted(signal_names)))
    return ". ".join(parts)


class Embedder:
    """Sentence-transformer embeddings when the package is installed; otherwise a hashed
    bag-of-words vector. The fallback only matches on shared codes and signal names, which is
    enough for "similar past cases" in the demo but is not semantic search."""

    def __init__(self) -> None:
        self._model = None
        self.backend = "hashing"
        if get_settings().enable_faiss:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                self.backend = "sentence-transformers/all-MiniLM-L6-v2"
            except Exception as exc:  # noqa: BLE001  (not installed, or no network for the first download)
                logger.info("embedder_fallback", reason=str(exc)[:120])

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._model is not None:
            return np.asarray(self._model.encode(texts, normalize_embeddings=True), dtype="float32")
        from sklearn.feature_extraction.text import HashingVectorizer

        vec = HashingVectorizer(n_features=DIM_FALLBACK, alternate_sign=False, norm="l2")
        return vec.transform(texts).toarray().astype("float32")


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
