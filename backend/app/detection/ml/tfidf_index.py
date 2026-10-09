import numpy as np


class TfidfIndex:
    """Similar-claim search with TF-IDF and cosine similarity (scikit-learn only: no PyTorch, no
    FAISS). Claims are described by their procedure codes, diagnosis codes and the names of the
    findings on them, so "similar" means "billed alike and flagged for the same reasons"."""

    method = "tfidf_cosine"

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.meta: list[dict] = []
        self.vectorizer = None
        self.matrix = None

    def __len__(self) -> int:
        return len(self.ids)

    def build(self, ids: list[str], texts: list[str], meta: list[dict] | None = None) -> "TfidfIndex":
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.ids, self.meta = list(ids), list(meta or [{} for _ in ids])
        if not ids:
            self.vectorizer = self.matrix = None
            return self
        # Codes such as I25.10 and E0601 are single tokens; rows are L2-normalised, so a dot
        # product is the cosine similarity.
        self.vectorizer = TfidfVectorizer(token_pattern=r"[A-Za-z0-9_.]+", lowercase=True, sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(texts)
        return self

    def search(self, text: str, k: int = 5, exclude: set[str] | None = None, min_similarity: float = 0.0, exclude_provider: str | None = None) -> list[dict]:
        if self.matrix is None or not text.strip():
            return []
        sims = np.asarray((self.matrix @ self.vectorizer.transform([text]).T).todense()).ravel()
        out = []
        for i in np.argsort(-sims):
            if len(out) >= k or sims[i] < max(min_similarity, 1e-9):
                break
            if exclude and self.ids[i] in exclude:
                continue
            if exclude_provider and self.meta[i].get("provider_id") == exclude_provider:
                continue
            out.append({"claim_id": self.ids[i], "similarity": round(float(sims[i]), 3), **self.meta[i]})
        return out
