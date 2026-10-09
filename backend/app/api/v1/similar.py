from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.exceptions import ValidationFailed
from app.deps import Ctx, require
from app.detection.ml.embeddings import claim_text
from app.detection.pipeline import claim_to_data
from app.schemas.common import Schema
from app.services import claim_service, similarity_service

router = APIRouter(tags=["similarity"])


class SimilarIn(Schema):
    claim_text: str | None = Field(default=None, max_length=4000, description="Free text: procedure codes, diagnosis codes, finding names")
    claim_id: str | None = Field(default=None, description="Use a stored claim as the query instead of text")
    k: int = Field(default=5, ge=1, le=50)


@router.post("/similar", summary="Find similar historical claims (TF-IDF cosine similarity)")
async def similar(body: SimilarIn, ctx: Ctx = Depends(require("cases:read"))):
    exclude = None
    text = body.claim_text
    if body.claim_id:
        claim = await claim_service.get(ctx.db, ctx.tenant.id, body.claim_id)
        names = [s.rule_name or s.model_name or s.pattern_name or "" for s in await claim_service.signals(ctx.db, ctx.tenant.id, claim) if s.detector != "similarity"]
        text, exclude = claim_text(claim_to_data(claim), names), {claim.claim_id}
    if not text or not text.strip():
        raise ValidationFailed("Send claim_text or claim_id.")
    out = await similarity_service.search_text(ctx.db, ctx.tenant, text, body.k, exclude)
    return {"query": text, **out}
