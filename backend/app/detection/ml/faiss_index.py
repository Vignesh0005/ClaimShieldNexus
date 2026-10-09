import numpy as np

from app.core.logging import logger


class SimilarityIndex:
    """Cosine nearest-neighbour search over case embeddings. Uses FAISS when installed and exact
    numpy search otherwise; results are identical for the index sizes a single tenant produces."""

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.meta: list[dict] = []
        self.vectors: np.ndarray | None = None
        self._faiss = None
        self.backend = "numpy"

    def build(self, ids: list[str], vectors: np.ndarray, meta: list[dict] | None = None) -> None:
        self.ids, self.meta = list(ids), list(meta or [{} for _ in ids])
        self.vectors = np.asarray(vectors, dtype="float32") if len(ids) else None
        self._faiss = None
        self.backend = "numpy"
        if self.vectors is None:
            return
        try:
            import faiss

            index = faiss.IndexFlatIP(self.vectors.shape[1])
            index.add(self.vectors)
            self._faiss, self.backend = index, "faiss"
        except Exception as exc:  # noqa: BLE001
            logger.debug("faiss_unavailable", reason=str(exc)[:80])

    def search(self, vector: np.ndarray, k: int = 5, exclude: str | None = None) -> list[dict]:
        if self.vectors is None or not len(self.ids):
            return []
        q = np.asarray(vector, dtype="float32").reshape(1, -1)
        n = min(k + 1, len(self.ids))
        if self._faiss is not None:
            scores, idx = self._faiss.search(q, n)
            pairs = list(zip(idx[0].tolist(), scores[0].tolist()))
        else:
            sims = (self.vectors @ q.T).ravel()
            order = np.argsort(-sims)[:n]
            pairs = [(int(i), float(sims[i])) for i in order]
        out = [{"id": self.ids[i], "similarity": round(s, 3), **self.meta[i]} for i, s in pairs if i >= 0 and self.ids[i] != exclude]
        return out[:k]
