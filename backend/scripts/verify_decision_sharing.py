"""Verify live decision snapshot without printing internal notes or credentials."""
import asyncio
import json
import urllib.request
from urllib.parse import quote
from sqlalchemy import select
from app.core.security import create_access_token
from app.db.session import get_sessionmaker
from app.models import Tenant, User, Claim, CaseDecision

async def main():
    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=15) as response:
        assert json.load(response)["status"] == "ok"
    async with get_sessionmaker()() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "demo_tenant"))).scalar_one()
        assert (tenant.config or {}).get("integration_share_decision_details") is True
        admin = (await db.execute(select(User).where(User.tenant_id == tenant.id, User.role == "admin", User.active.is_(True)))).scalars().first()
        token = create_access_token(subject=admin.external_id, tenant_id=tenant.id, role="admin", minutes=5)
        claim = (await db.execute(select(Claim).where(Claim.tenant_id == tenant.id, Claim.case_ref.is_not(None)).order_by(Claim.created_at.desc()))).scalars().first()
        if claim is None:
            claim = (await db.execute(select(Claim).where(Claim.tenant_id == tenant.id))).scalars().first()
        if claim is None:
            raise RuntimeError("No existing claim to verify")
        decision = (await db.execute(select(CaseDecision).where(CaseDecision.tenant_id == tenant.id, CaseDecision.case_id == claim.case_ref).order_by(CaseDecision.decided_at.desc()).limit(1))).scalar_one_or_none() if claim.case_ref else None
        expected_notes = decision.notes if decision else None
        expected_reviewer = (decision.decided_by_label or (str(decision.decided_by) if decision.decided_by else None)) if decision else None
        claim_id = claim.claim_id
    url = "http://127.0.0.1:8000/api/v1/integrations/claims/" + quote(claim_id, safe="") + "/result"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + token}), timeout=15) as response:
        result = json.load(response)
    assert "notes" in result and "decided_by" in result
    assert result["notes"] == expected_notes and result["decided_by"] == expected_reviewer
    print("Backend healthy; live snapshot fields verified against recorded decision. Existing decision:", decision is not None)

if __name__ == "__main__":
    asyncio.run(main())
