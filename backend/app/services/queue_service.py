import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.detection.scoring.capacity_optimizer import CapacityOptimizer, QueueCase
from app.models import OPEN_STATUSES, Case, Claim, DetectionSignal, Tenant
from app.schemas.case import OptimizeIn
from app.services import case_service


async def open_cases(db: AsyncSession, tenant_id: uuid.UUID) -> list[Case]:
    rows = await db.execute(select(Case).where(Case.tenant_id == tenant_id, Case.status.in_(OPEN_STATUSES)).order_by(Case.risk_score.desc().nulls_last()))
    return list(rows.scalars().all())


def _queue_case(c: Case) -> QueueCase:
    return QueueCase(c.case_id, c.provider_id, c.risk_score or 0.0, float(c.expected_recovery or 0), c.member_harm_score or 0.0, c.estimated_hours or 4.0, c.evidence_strength or 0.0)


def _selected_dict(c: QueueCase) -> dict:
    return {
        "case_id": c.case_id, "provider_id": c.provider_id, "risk_score": c.risk_score, "expected_recovery": c.expected_recovery,
        "member_harm_score": c.member_harm_score, "estimated_hours": c.estimated_hours, "evidence_strength": c.evidence_strength,
    }


async def optimize(db: AsyncSession, tenant: Tenant, params: OptimizeIn) -> dict:
    cases = await open_cases(db, tenant.id)
    result = CapacityOptimizer().optimize([_queue_case(c) for c in cases], params.num_investigators, params.hours_per_investigator, params.min_evidence_strength, params.max_cases)
    return {
        "selected_cases": [_selected_dict(c) for c in result.selected_cases],
        "total_selected": len(result.selected_cases),
        "total_hours": result.total_hours,
        "capacity": result.capacity,
        "total_expected_recovery": result.total_expected_recovery,
        "total_harm_reduction": result.total_harm_reduction,
        "skipped_low_evidence": result.skipped_low_evidence,
        "optimization_method": result.optimization_method,
        "open_cases": len(cases),
    }


def default_capacity(tenant: Tenant) -> OptimizeIn:
    cap = (tenant.config or {}).get("capacity") or {}
    return OptimizeIn(num_investigators=cap.get("num_investigators", 3), hours_per_investigator=cap.get("hours_per_investigator", 20))


async def ranked(db: AsyncSession, tenant: Tenant, params: OptimizeIn | None = None) -> dict:
    """The open queue in priority order, with a marker on the cases that fit current capacity."""
    params = params or default_capacity(tenant)
    plan = await optimize(db, tenant, params)
    selected = {c["case_id"] for c in plan["selected_cases"]}
    cases = await open_cases(db, tenant.id)
    users = await case_service._users(db, tenant.id, {c.assigned_to for c in cases if c.assigned_to})
    providers = await case_service.provider_map(db, tenant.id, {c.provider_id for c in cases})
    metrics.queue_size.labels(str(tenant.id)).set(len(cases))
    return {
        "capacity": {k: plan[k] for k in ("capacity", "total_hours", "total_selected", "total_expected_recovery", "total_harm_reduction", "skipped_low_evidence", "optimization_method")},
        "cases": [{**case_service.summary(c, users.get(c.assigned_to), providers.get(c.provider_id)), "rank": i + 1, "in_capacity": c.case_id in selected} for i, c in enumerate(cases)],
        "total": len(cases),
    }


async def stats(db: AsyncSession, tenant: Tenant) -> dict:
    t = tenant.id
    by_status = dict((await db.execute(select(Case.status, func.count()).where(Case.tenant_id == t).group_by(Case.status))).all())
    by_severity = dict((await db.execute(select(Case.severity, func.count()).where(Case.tenant_id == t, Case.status.in_(OPEN_STATUSES)).group_by(Case.severity))).all())
    hours, dollars, unassigned = (
        await db.execute(
            select(func.coalesce(func.sum(Case.estimated_hours), 0), func.coalesce(func.sum(Case.expected_recovery), 0), func.count().filter(Case.assigned_to.is_(None))).where(Case.tenant_id == t, Case.status.in_(OPEN_STATUSES))
        )
    ).one()
    return {
        "open_cases": sum(by_status.get(s, 0) for s in OPEN_STATUSES),
        "by_status": by_status,
        "open_by_severity": by_severity,
        "open_review_hours": float(hours),
        "open_dollars_at_risk": float(dollars),
        "unassigned": int(unassigned),
    }


async def funnel(db: AsyncSession, tenant: Tenant) -> dict:
    """Claims -> alerts (claims with at least one finding) -> clusters (cases) -> SIU cases
    (cases that fit the tenant's review capacity)."""
    t = tenant.id
    claims = (await db.execute(select(func.count()).select_from(Claim).where(Claim.tenant_id == t))).scalar_one()
    alerts = (await db.execute(select(func.count(func.distinct(DetectionSignal.claim_id))).where(DetectionSignal.tenant_id == t))).scalar_one()
    clusters = (await db.execute(select(func.count()).select_from(Case).where(Case.tenant_id == t))).scalar_one()
    plan = await optimize(db, tenant, default_capacity(tenant))
    siu = plan["total_selected"]
    severity = dict((await db.execute(select(Claim.severity, func.count()).where(Claim.tenant_id == t, Claim.id.in_(select(DetectionSignal.claim_id).where(DetectionSignal.tenant_id == t))).group_by(Claim.severity))).all())
    coverage_review = (await db.execute(select(func.count()).select_from(Claim).where(Claim.tenant_id == t, Claim.coverage_status.in_(("NOT_COVERABLE", "COVERAGE_REVIEW_REQUIRED"))))).scalar_one()
    return {
        "stages": [
            {"key": "claims", "label": "Claims", "value": claims},
            {"key": "alerts", "label": "Alerts", "value": alerts},
            {"key": "clusters", "label": "Clusters", "value": clusters},
            {"key": "cases", "label": "SIU cases", "value": siu},
        ],
        "reduction_pct": round((1 - siu / claims) * 100, 1) if claims else 0.0,
        "alerts_by_severity": {k or "unscored": v for k, v in severity.items()},
        "coverage_review_required": coverage_review,
        "dollars_at_risk": (await stats(db, tenant))["open_dollars_at_risk"],
    }


async def dashboard(db: AsyncSession, tenant: Tenant) -> dict:
    """Everything the overview screen shows, computed from stored data. Periods are the last 30
    days of service dates against the 30 days before, ending at the tenant's latest claim."""
    from datetime import timedelta

    from app.detection.scoring.severity import severity
    from app.models import AuditLog

    t = tenant.id
    latest = (await db.execute(select(func.max(Claim.service_date)).where(Claim.tenant_id == t))).scalar_one()
    periods = {}
    if latest is not None:
        cur_start, prev_start = latest - timedelta(days=30), latest - timedelta(days=60)
        flagged = select(DetectionSignal.claim_id).where(DetectionSignal.tenant_id == t)
        for name, lo, hi in (("current", cur_start, latest), ("previous", prev_start, cur_start)):
            window = [Claim.tenant_id == t, Claim.service_date > lo, Claim.service_date <= hi]
            n = (await db.execute(select(func.count()).select_from(Claim).where(*window))).scalar_one()
            alerts = (await db.execute(select(func.count()).select_from(Claim).where(*window, Claim.id.in_(flagged)))).scalar_one()
            routed, dollars = (await db.execute(select(func.count(), func.coalesce(func.sum(Claim.total_billed), 0)).where(*window, Claim.case_ref.isnot(None)))).one()
            periods[name] = {"claims": n, "alerts": alerts, "routed_claims": routed, "routed_dollars": float(dollars)}
    top = (
        await db.execute(
            select(Case.provider_id, func.sum(Case.expected_recovery), func.max(Case.risk_score), func.min(Case.case_id))
            .where(Case.tenant_id == t, Case.status.in_(OPEN_STATUSES), Case.provider_id.isnot(None))
            .group_by(Case.provider_id).order_by(func.sum(Case.expected_recovery).desc()).limit(5)
        )
    ).all()
    notable = ("case.created", "case.decision", "case.assigned", "case.status_changed", "model.deployed", "model.retrained", "demo.scheme_injected", "feedback.submitted", "tenant.config_updated", "tenant.field_mapping_updated")
    events = (await db.execute(select(AuditLog).where(AuditLog.tenant_id == t, AuditLog.action.in_(notable)).order_by(AuditLog.timestamp.desc()).limit(8))).scalars().all()
    return {
        "funnel": await funnel(db, tenant),
        "period_days": 30,
        "as_of": latest,
        "periods": periods,
        "top_providers": [{"provider_id": p, "expected_recovery": float(d or 0), "risk_score": r, "severity": severity(r or 0, (tenant.config or {}).get("thresholds")), "case_id": c} for p, d, r, c in top],
        "activity": [{"id": str(e.id), "action": e.action, "actor": e.actor_label, "resource_id": e.resource_id, "details": e.details, "timestamp": e.timestamp} for e in events],
    }
