"""Builds the similar-cases index for a tenant from its reviewed cases and prints a sample query.

    python -m scripts.build_faiss_index --tenant meridian [--out artifacts/similar_meridian.npz]

Uses sentence-transformers and FAISS when installed (requirements-ml-extras.txt); otherwise a
hashed bag-of-codes embedding and exact search, which the output states."""
import argparse
import asyncio

import numpy as np
from sqlalchemy import select

from app.db.session import dispose_engine, session_scope
from app.detection.ml.embeddings import claim_text, get_embedder
from app.detection.ml.faiss_index import SimilarityIndex
from app.detection.pipeline import claim_to_data
from app.models import Case, Claim
from app.services import tenant_service


async def main(slug: str, out: str | None) -> None:
    async with session_scope() as db:
        tenant = await tenant_service.get_by_slug(db, slug)
        db.info["tenant_id"] = tenant.id
        cases = (await db.execute(select(Case).where(Case.tenant_id == tenant.id, Case.primary_claim_id.isnot(None)))).scalars().all()
        ids, texts, meta = [], [], []
        for case in cases:
            claim = await db.get(Claim, case.primary_claim_id)
            if claim is None:
                continue
            ids.append(case.case_id)
            texts.append(claim_text(claim_to_data(claim), (case.summary or {}).get("signal_names")))
            meta.append({"status": case.status, "severity": case.severity, "primary_flag": (case.summary or {}).get("primary_flag")})
    await dispose_engine()
    if not ids:
        print(f"Tenant '{slug}' has no cases to index.")
        return
    embedder = get_embedder()
    vectors = embedder.encode(texts)
    index = SimilarityIndex()
    index.build(ids, vectors, meta)
    print(f"Indexed {len(ids)} cases. Embeddings: {embedder.backend}. Search: {index.backend}.")
    print(f"Cases most similar to {ids[0]}:")
    for hit in index.search(vectors[0], k=3, exclude=ids[0]):
        print(f"  {hit['id']}  similarity {hit['similarity']}  ({hit.get('primary_flag')}, {hit.get('status')})")
    if out:
        np.savez_compressed(out, ids=np.array(ids), vectors=vectors)
        print(f"Saved to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    asyncio.run(main(args.tenant, args.out))
