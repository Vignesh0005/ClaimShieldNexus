from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.db.session import bind_tenant
from app.deps import Ctx, platform_admin, require
from app.detection.context import ClaimData
from app.detection.temporal.baseline import weekly_series
from app.detection.temporal.forecast import MODEL_VERSION, forecast_provider
from app.models import Case, Claim, ProviderForecast, Tenant
from app.services import queue_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", summary="Per-tenant totals (platform admin)")
async def overview(ctx: Ctx = Depends(platform_admin)):
    bind_tenant(ctx.db, None)
    tenants = (await ctx.db.execute(select(Tenant).order_by(Tenant.created_at))).scalars().all()
    claims = dict((await ctx.db.execute(select(Claim.tenant_id, func.count()).group_by(Claim.tenant_id))).all())
    cases = dict((await ctx.db.execute(select(Case.tenant_id, func.count()).group_by(Case.tenant_id))).all())
    return {"tenants": [{"id": str(t.id), "slug": t.slug, "name": t.name, "active": t.active, "is_demo": t.is_demo, "claims": claims.get(t.id, 0), "cases": cases.get(t.id, 0)} for t in tenants]}


@router.post("/tenants/{slug}/active", summary="Activate or suspend a tenant (platform admin)")
async def set_active(slug: str, active: bool, ctx: Ctx = Depends(platform_admin)):
    bind_tenant(ctx.db, None)
    tenant = (await ctx.db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()
    tenant.active = active
    await ctx.audit.log("tenant.activated" if active else "tenant.suspended", "tenant", slug, principal=ctx.principal, tenant_id=tenant.id, request=ctx.request)
    await ctx.db.commit()
    return {"slug": slug, "active": active}


@router.get("/analytics", summary="Executive analytics for the tenant")
async def analytics(ctx: Ctx = Depends(require("analytics:read"))):
    t = ctx.tenant.id
    daily = (await ctx.db.execute(select(Claim.service_date, func.count(), func.coalesce(func.sum(Claim.total_billed), 0), func.count().filter(Claim.risk_score >= 0.7)).where(Claim.tenant_id == t, Claim.service_date.isnot(None)).group_by(Claim.service_date))).all()
    months: dict[str, list[float]] = {}
    for d, n, billed, routed in daily:
        m = months.setdefault(d.strftime("%Y-%m"), [0, 0.0, 0])
        m[0] += n
        m[1] += float(billed)
        m[2] += int(routed)
    monthly = [(k, *v) for k, v in sorted(months.items())]
    by_flag = (await ctx.db.execute(select(Case.severity, func.count(), func.coalesce(func.sum(Case.expected_recovery), 0)).where(Case.tenant_id == t).group_by(Case.severity))).all()
    detail = await _analytics_detail(ctx)
    return {
        **detail,
        "monthly": [{"month": m, "claims": n, "billed": float(b), "routed": int(r), **detail["monthly_extra"].get(m, {})} for m, n, b, r in monthly if m],
        "cases_by_severity": [{"severity": s, "cases": n, "dollars": float(d)} for s, n, d in by_flag],
        "queue": await queue_service.stats(ctx.db, ctx.tenant),
        "funnel": await queue_service.funnel(ctx.db, ctx.tenant),
    }


async def _analytics_detail(ctx: Ctx) -> dict:
    """Breakdowns computed from cases and recorded decisions. Anything the system does not track
    (money actually recovered) is returned as null rather than estimated."""
    from app.models import OPEN_STATUSES, CaseDecision, DetectionSignal, User
    from app.services import case_service

    t = ctx.tenant.id
    cases = (await ctx.db.execute(select(Case).where(Case.tenant_id == t))).scalars().all()
    providers = await case_service.provider_map(ctx.db, t, {c.provider_id for c in cases})
    users = dict((await ctx.db.execute(select(User.id, User.name).where(User.tenant_id == t))).all())

    flagged = (await ctx.db.execute(select(Claim.service_date, func.count(), func.coalesce(func.sum(Claim.total_billed).filter(Claim.case_ref.isnot(None)), 0)).where(Claim.tenant_id == t, Claim.service_date.isnot(None), Claim.id.in_(select(DetectionSignal.claim_id).where(DetectionSignal.tenant_id == t))).group_by(Claim.service_date))).all()
    extra: dict[str, dict] = {}
    for d, n, dollars in flagged:
        m = extra.setdefault(d.strftime("%Y-%m"), {"alerts": 0, "identified": 0.0, "cases_opened": 0})
        m["alerts"] += n
        m["identified"] += float(dollars or 0)
    for c in cases:
        extra.setdefault(c.created_at.strftime("%Y-%m"), {"alerts": 0, "identified": 0.0, "cases_opened": 0})["cases_opened"] += 1

    by_flag: dict[str, dict] = {}
    heat: dict[tuple[str, str], int] = {}
    workload: dict[str, dict] = {}
    for c in cases:
        flag = (c.summary or {}).get("primary_flag") or "unclassified"
        entry = by_flag.setdefault(flag, {"flag": flag, "cases": 0, "amount": 0.0})
        entry["cases"] += 1
        entry["amount"] += float(c.expected_recovery or 0)
        specialty = (providers.get(c.provider_id) or (None, None))[1] or "Unknown"
        heat[(flag, specialty)] = heat.get((flag, specialty), 0) + 1
        if c.assigned_to:
            w = workload.setdefault(str(c.assigned_to), {"investigator": users.get(c.assigned_to) or "Unknown", "open": 0, "closed": 0, "hours": []})
            w["open" if c.status in OPEN_STATUSES else "closed"] += 1
            w["hours"].append(c.estimated_hours or 0)

    decisions = (await ctx.db.execute(select(CaseDecision.decision, CaseDecision.decided_at, Case.created_at).join(Case, Case.id == CaseDecision.case_id).where(CaseDecision.tenant_id == t))).all()
    confirmed = sum(1 for d, _, _ in decisions if d == "confirm_fraud")
    dismissed = sum(1 for d, _, _ in decisions if d == "false_positive")
    days = [(decided - created).total_seconds() / 86400 for _, decided, created in decisions if decided and created]
    return {
        "monthly_extra": extra,
        "by_flag": sorted(by_flag.values(), key=lambda x: -x["amount"]),
        "heatmap": [{"flag": f, "specialty": s, "cases": n} for (f, s), n in sorted(heat.items())],
        "workload": [{"investigator": w["investigator"], "open": w["open"], "closed": w["closed"], "avg_estimated_hours": round(sum(w["hours"]) / len(w["hours"]), 1) if w["hours"] else None} for w in workload.values()],
        "decisions": {
            "total": len(decisions), "confirmed": confirmed, "false_positive": dismissed,
            "reviewer_confirmed_rate": round(confirmed / (confirmed + dismissed), 3) if confirmed + dismissed else None,
            "avg_days_to_decision": round(sum(days) / len(days), 2) if days else None,
        },
        "dollars_identified": round(sum(float(c.expected_recovery or 0) for c in cases), 2),
        "dollars_recovered": None,  # recoveries are not tracked by this system
    }


@router.get("/logs", summary="Recent application log events from this process (platform admin)")
async def recent_logs(ctx: Ctx = Depends(platform_admin), limit: int = 200):
    from app.core.logging import RECENT_LOGS

    return {"logs": list(RECENT_LOGS)[-limit:][::-1], "note": "In-memory, this API process only. Use your log platform for history."}


@router.post("/forecasts/run", summary="Compute 30/60/90-day provider forecasts now")
async def run_forecasts(ctx: Ctx = Depends(require("models:deploy"))):
    return {"forecasts_written": await compute_forecasts(ctx.db, ctx.tenant.id), "model_version": MODEL_VERSION}


@router.get("/forecasts", summary="Latest provider forecasts")
async def forecasts(ctx: Ctx = Depends(require("analytics:read")), horizon_days: int = 30):
    latest = (await ctx.db.execute(select(func.max(ProviderForecast.forecast_date)).where(ProviderForecast.tenant_id == ctx.tenant.id))).scalar_one()
    rows = (
        await ctx.db.execute(
            select(ProviderForecast).where(ProviderForecast.tenant_id == ctx.tenant.id, ProviderForecast.forecast_date == latest, ProviderForecast.horizon_days == horizon_days).order_by(ProviderForecast.risk_probability.desc()).limit(100)
        )
    ).scalars().all()
    return {"forecast_date": latest, "horizon_days": horizon_days, "method": MODEL_VERSION, "providers": [{"provider_id": f.provider_id, "risk_probability": f.risk_probability, "predicted_dollars": f.predicted_dollars} for f in rows]}


async def compute_forecasts(db, tenant_id) -> int:
    """Forecasts for providers that have an open case. Replaces today's rows so it can be re-run."""
    today = (await db.execute(select(func.max(Claim.service_date)).where(Claim.tenant_id == tenant_id))).scalar_one() or date.today()
    cases = (await db.execute(select(Case.provider_id, func.max(Case.risk_score)).where(Case.tenant_id == tenant_id, Case.provider_id.isnot(None)).group_by(Case.provider_id))).all()
    existing = (await db.execute(select(ProviderForecast).where(ProviderForecast.tenant_id == tenant_id, ProviderForecast.forecast_date == today))).scalars().all()
    for row in existing:
        await db.delete(row)
    await db.flush()
    written = 0
    for provider_id, risk in cases:
        rows = await db.execute(select(Claim.service_date, Claim.total_billed).where(Claim.tenant_id == tenant_id, Claim.provider_id == provider_id, Claim.service_date >= today - timedelta(days=182)))
        history = [ClaimData(claim_id="", service_date=d, total_billed=float(b or 0)) for d, b in rows.all()]
        for f in forecast_provider(weekly_series(history, today, weeks=26), risk):
            db.add(ProviderForecast(tenant_id=tenant_id, provider_id=provider_id, forecast_date=today, model_version=MODEL_VERSION, **f))
            written += 1
    await db.commit()
    return written
