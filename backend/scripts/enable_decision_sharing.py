"""Enable approved decision sharing for the existing mock insurer tenant only."""
import asyncio
import json
import urllib.request
from sqlalchemy import select
from app.core.security import create_access_token
from app.db.session import get_sessionmaker
from app.models import Tenant, User

async def main():
    async with get_sessionmaker()() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "demo_tenant", Tenant.active.is_(True)))).scalar_one()
        admin = (await db.execute(select(User).where(User.tenant_id == tenant.id, User.role == "admin", User.active.is_(True)))).scalars().first()
        if admin is None:
            raise RuntimeError("No active tenant administrator exists")
        token = create_access_token(subject=admin.external_id, tenant_id=tenant.id, role="admin", minutes=5)
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    url = "http://127.0.0.1:8000/api/v1/tenants/demo_tenant/config"
    request = urllib.request.Request(url, data=json.dumps({"config": {"integration_share_decision_details": True}}).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    assert result["config"]["integration_share_decision_details"] is True
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
        verified = json.load(response)
    assert verified["config"]["integration_share_decision_details"] is True
    print("Verified: Mock Insurer Demo decision sharing enabled through audited admin API.")

if __name__ == "__main__":
    asyncio.run(main())
