"""Model server for the two-machine setup. Run on the training machine:

    uvicorn scripts.ml_server:app --host 0.0.0.0 --port 8001

and set ML_SERVER_URL=http://<training-machine>:8001 on the application server. It serves the
version named in artifacts/CURRENT and only ever receives feature vectors, never claims.

Set ML_SERVER_TOKEN to require `Authorization: Bearer <token>`; expose it only on a trusted network."""
import os

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.detection.ml.embeddings import get_embedder
from app.detection.ml.faiss_index import SimilarityIndex
from app.detection.ml.registry import ModelRegistry

app = FastAPI(title="ClaimShield model server", version="0.1.0", docs_url=None, redoc_url=None)
models = ModelRegistry()
index = SimilarityIndex()


def authorised(authorization: str | None = Header(default=None)) -> None:
    token = os.environ.get("ML_SERVER_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Invalid token")


class PredictIn(BaseModel):
    features: dict[str, float]


class SimilarIn(BaseModel):
    claim_text: str
    k: int = 5


class IndexIn(BaseModel):
    ids: list[str]
    texts: list[str]


@app.get("/health")
def health():
    loaded = models.load()
    return {"status": "ok" if loaded else "no_model", "model_version": models.version, "indexed_cases": len(index.ids)}


@app.post("/predict", dependencies=[Depends(authorised)])
def predict(body: PredictIn):
    prediction = models.predict(body.features)
    if prediction.fraud_probability is None:
        raise HTTPException(status_code=503, detail="No model is deployed on this server. Run scripts.train_xgboost first.")
    return prediction.__dict__


@app.post("/index", dependencies=[Depends(authorised)])
def build_index(body: IndexIn):
    index.build(body.ids, get_embedder().encode(body.texts) if body.texts else np.zeros((0, 1)))
    return {"indexed": len(index.ids), "backend": index.backend, "embedder": get_embedder().backend}


@app.post("/similar", dependencies=[Depends(authorised)])
def similar(body: SimilarIn):
    if not index.ids:
        return {"similar_cases": []}
    return {"similar_cases": index.search(get_embedder().encode([body.claim_text])[0], body.k)}
