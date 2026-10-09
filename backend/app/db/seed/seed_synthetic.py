from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ClaimShieldException
from app.db.seed.synthetic import SyntheticData, public_claim
from app.models import Claim, Facility, Member, Provider, Tenant
from app.services import claim_service
from app.utils.dates import parse_date


async def seed_reference_data(db: AsyncSession, tenant: Tenant, data: SyntheticData) -> None:
    have = set((await db.execute(select(Provider.provider_id).where(Provider.tenant_id == tenant.id))).scalars().all())
    for p in data.providers:
        if p["provider_id"] not in have:
            db.add(Provider(tenant_id=tenant.id, **p))
    have = set((await db.execute(select(Member.member_id).where(Member.tenant_id == tenant.id))).scalars().all())
    for m in data.members:
        if m["member_id"] not in have:
            db.add(Member(tenant_id=tenant.id, member_id=m["member_id"], age=m["age"], postal_code=m["postal_code"], low_income_area=m["low_income_area"], plan_type=m["plan_type"], policy_start_date=parse_date(m["policy_start_date"])))
    have = set((await db.execute(select(Facility.facility_id).where(Facility.tenant_id == tenant.id))).scalars().all())
    for f in data.facilities:
        if f["facility_id"] not in have:
            db.add(Facility(tenant_id=tenant.id, **f))
    await db.flush()


async def seed_claims(db: AsyncSession, tenant: Tenant, data: SyntheticData, progress=None) -> dict:
    """Sends every synthetic claim through the real ingest path and detection pipeline, in date
    order, so cases form the same way they would from a live feed. Re-running skips claims that
    are already stored."""
    stats = {"ingested": 0, "skipped": 0, "rejected": 0}
    for i, raw in enumerate(data.claims):
        try:
            async with db.begin_nested():
                _, duplicate, _ = await claim_service.ingest_record(db, tenant, public_claim(raw), source="seed", process=True)
            stats["skipped" if duplicate else "ingested"] += 1
        except ClaimShieldException:
            stats["rejected"] += 1
        if (i + 1) % 100 == 0:
            await db.commit()
            if progress:
                progress(i + 1, len(data.claims))
    await db.commit()
    stats["total_in_tenant"] = (await db.execute(select(func.count()).select_from(Claim).where(Claim.tenant_id == tenant.id))).scalar_one()
    return stats
