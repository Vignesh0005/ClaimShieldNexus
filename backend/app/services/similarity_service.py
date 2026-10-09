"""Similar-case retrieval. For a flagged claim, finds earlier claims that were billed alike and
flagged for the same reasons, so a reviewer can see how comparable cases turned out.

The result is context for the reviewer. It is stored as a signal so it appears in the evidence
trail and the brief, but it is never used in the risk score."""
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.detection.context import ClaimData
from app.detection.ml.embeddings import claim_text
from app.detection.ml.tfidf_index import TfidfIndex
from app.detection.pipeline import claim_to_data
from app.models import Case, Claim, DetectionSignal, Tenant

MAX_CORPUS = 5000
MIN_SIMILARITY = 0.35
CONFIRMED = ("confirmed", "escalated")

_cache: dict[uuid.UUID, dict] = {}


def invalidate(tenant_id: uuid.UUID) -> None:
    entry = _cache.get(tenant_id)
    if entry:
        entry["dirty"] = True


def corpus_mode(tenant: Tenant) -> str:
    """"all_cases" (default): every claim that belongs to a case, each labelled with the case's
    current status. "confirmed_only": only claims in cases a reviewer confirmed. A new deployment
    has no confirmed cases yet, so the stricter mode returns nothing until reviewers decide some."""
    return ((tenant.config or {}).get("similarity") or {}).get("corpus", "all_cases")


async def build_index(db: AsyncSession, tenant: Tenant) -> TfidfIndex:
    where = [Claim.tenant_id == tenant.id, Case.tenant_id == tenant.id]
    if corpus_mode(tenant) == "confirmed_only":
        where.append(Case.status.in_(CONFIRMED))
    rows = (await db.execute(select(Claim, Case.case_id, Case.status, Case.summary).join(Case, Case.id == Claim.case_ref).where(*where).order_by(Claim.created_at.desc()).limit(MAX_CORPUS))).all()
    names: dict[uuid.UUID, list[str]] = {}
    if rows:
        signals = await db.execute(select(DetectionSignal.claim_id, DetectionSignal.rule_name, DetectionSignal.model_name, DetectionSignal.pattern_name).where(DetectionSignal.tenant_id == tenant.id, DetectionSignal.detector != "similarity", DetectionSignal.claim_id.in_([c.id for c, *_ in rows])))
        for claim_id, rule, model, pattern in signals.all():
            names.setdefault(claim_id, []).append(rule or model or pattern or "")
    ids, texts, meta = [], [], []
    for claim, case_id, status, summary in rows:
        ids.append(claim.claim_id)
        texts.append(claim_text(claim_to_data(claim), names.get(claim.id)))
        meta.append({"case_id": case_id, "case_status": status, "outcome": "confirmed by a reviewer" if status in CONFIRMED else "closed as false positive" if status == "false_positive" else "not yet reviewed", "primary_flag": (summary or {}).get("primary_flag"), "provider_id": claim.provider_id})
    return TfidfIndex().build(ids, texts, meta)


async def index_for(db: AsyncSession, tenant: Tenant) -> TfidfIndex:
    entry = _cache.get(tenant.id)
    now = time.monotonic()
    # Small corpora rebuild as soon as a case changes; large ones at most every 30 seconds.
    if entry is None or entry["mode"] != corpus_mode(tenant) or now - entry["built"] > 300 or (entry["dirty"] and (len(entry["index"]) < 300 or now - entry["built"] > 30)):
        entry = {"index": await build_index(db, tenant), "built": now, "dirty": False, "mode": corpus_mode(tenant)}
        _cache[tenant.id] = entry
    return entry["index"]


async def similar_to_claim(db: AsyncSession, tenant: Tenant, claim: ClaimData, signal_names: list[str], k: int = 5) -> list[dict]:
    index = await index_for(db, tenant)
    # The provider's own earlier claims are already used by the rules as history. Similar cases
    # are about other providers: has this pattern been seen elsewhere, and how did it turn out?
    return index.search(claim_text(claim, signal_names), k=k, exclude={claim.claim_id}, min_similarity=MIN_SIMILARITY, exclude_provider=claim.provider_id)


async def search_text(db: AsyncSession, tenant: Tenant, text: str, k: int = 5, exclude: set[str] | None = None) -> dict:
    index = await index_for(db, tenant)
    return {"similar_cases": index.search(text, k=k, exclude=exclude), "method": TfidfIndex.method, "corpus": corpus_mode(tenant), "corpus_size": len(index), "note": "Similarity is over procedure codes, diagnosis codes and finding names. It is context for a reviewer and is not used in the risk score."}
