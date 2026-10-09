"""Injects synthetic test schemes into a demo tenant through the real pipeline and prints what
each detector reported. The same code path as POST /api/v1/inject.

    python -m scripts.plant_fraud_schemes --tenant meridian [--scheme referral_ring]"""
import argparse
import asyncio

from app.config import get_settings
from app.core.logging import configure_logging
from app.core.security import Principal, Role
from app.db.session import dispose_engine, session_scope
from app.services import inject_service, tenant_service


async def main(slug: str, scheme: str | None) -> None:
    get_settings().log_level = "WARNING"
    configure_logging()
    schemes = [scheme] if scheme else list(inject_service.SCHEMES)
    async with session_scope() as db:
        tenant = await tenant_service.get_by_slug(db, slug)
    rows = []
    for name in schemes:
        async with session_scope(tenant.id) as db:
            out = await inject_service.inject(db, tenant, name, Principal(tenant.id, Role.ADMIN, "script", actor_type="system"))
        rows.append((name, out["composite_risk"], out["max_rule_confidence"], out["risk_score"], "yes" if out["routed"] else "no", out["case_opening_reason"] or "-", out["case_id"] or "-", f"{out['latency_ms']} ms"))
    header = ("scheme", "composite_risk", "max_rule_conf", "risk_score", "opened", "reason", "case", "latency")
    widths = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    for r in [header] + rows:
        print(" | ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    print(f"{sum(1 for r in rows if r[4] == 'yes')} of {len(rows)} schemes opened a case.")
    await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="meridian")
    parser.add_argument("--scheme", choices=list(inject_service.SCHEMES))
    args = parser.parse_args()
    asyncio.run(main(args.tenant, args.scheme))
