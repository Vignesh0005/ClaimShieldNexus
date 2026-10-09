import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.events import event_bus
from app.core.exceptions import NotFound, ValidationFailed
from app.core.security import Principal
from app.db.base import utcnow
from app.detection.context import Signal
from app.detection.graph.builder import ClaimEdge, ReferralEdge, build_bipartite_graph
from app.detection.graph.visualizer import export_graph
from app.detection.scoring.fusion import dollar_impact
from app.explainability import counterfactuals as cf
from app.explainability.plain_language import label, plain
from app.explainability.uncertainty import limitations as build_limitations
from app.models import OPEN_STATUSES, Case, CaseDecision, Claim, Counterfactual, DetectionSignal, ModelFeedback, Provider, Referral, Tenant, User
from app.schemas.case import DECISION_LABEL, DECISION_STATUS, DecisionIn
from app.services import tenant_service


def _model_warning(version: str | None) -> str | None:
    from app.detection.ml.training import SYNTHETIC_WARNING

    return SYNTHETIC_WARNING if version and not version.startswith("fallback") else None


# ---------- lookup ----------

async def get(db: AsyncSession, tenant_id: uuid.UUID, case_id: str) -> Case:
    case = (await db.execute(select(Case).where(Case.tenant_id == tenant_id, Case.case_id == case_id))).scalar_one_or_none()
    if case is None:
        raise NotFound(f"Case '{case_id}' not found.")
    return case


async def claims_of(db: AsyncSession, case: Case) -> list[Claim]:
    rows = await db.execute(select(Claim).where(Claim.tenant_id == case.tenant_id, Claim.case_ref == case.id).order_by(Claim.risk_score.desc().nulls_last()))
    return list(rows.scalars().all())


async def signals_of(db: AsyncSession, case: Case) -> list[dict]:
    """Strongest instance of each finding across the case's claims, each tagged with the claim it
    came from so it can be cited."""
    rows = await db.execute(
        select(DetectionSignal, Claim.claim_id)
        .join(Claim, Claim.id == DetectionSignal.claim_id)
        .where(DetectionSignal.tenant_id == case.tenant_id, Claim.tenant_id == case.tenant_id, Claim.case_ref == case.id)
        .order_by(DetectionSignal.score.desc())
    )
    best: dict[tuple[str, str], dict] = {}
    for s, claim_id in rows.all():
        name = s.rule_name or s.model_name or s.pattern_name or "unknown"
        key = (s.detector, name)
        if key not in best:
            best[key] = {"signal_id": s.signal_id, "detector": s.detector, "name": name, "label": label(name), "score": s.score or 0.0, "confidence": s.confidence, "severity": s.severity, "evidence": s.evidence or {}, "source_fields": s.source_fields or [], "claim_id": claim_id, "occurrences": 0}
        best[key]["occurrences"] += 1
    return sorted(best.values(), key=lambda x: x["score"], reverse=True)


async def _users(db: AsyncSession, tenant_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.external_id).where(User.tenant_id == tenant_id, User.id.in_(ids)))
    return dict(rows.all())


async def provider_map(db: AsyncSession, tenant_id: uuid.UUID, provider_ids: set[str | None]) -> dict[str, tuple[str | None, str | None]]:
    ids = {p for p in provider_ids if p}
    if not ids:
        return {}
    rows = await db.execute(select(Provider.provider_id, Provider.name, Provider.specialty).where(Provider.tenant_id == tenant_id, Provider.provider_id.in_(ids)))
    return {pid: (name, specialty) for pid, name, specialty in rows.all()}


WORKFLOW_STATUSES = ("pending_review", "in_review", "needs_info")


def summary(case: Case, assignee: str | None = None, provider: tuple[str | None, str | None] | None = None) -> dict:
    return {
        "provider_name": provider[0] if provider else None, "specialty": provider[1] if provider else None,
        "suspicion_score": case.suspicion_score, "opened_reason": (case.summary or {}).get("opened_reason"),
        "case_id": case.case_id, "provider_id": case.provider_id, "risk_score": case.risk_score, "severity": case.severity,
        "priority_tier": case.priority_tier, "member_harm_score": case.member_harm_score, "evidence_strength": case.evidence_strength,
        "expected_recovery": case.expected_recovery, "estimated_hours": case.estimated_hours, "claim_count": case.claim_count,
        "members_affected": case.members_affected, "status": case.status, "assigned_to": assignee,
        "primary_flag": (case.summary or {}).get("primary_flag"), "two_axis_quadrant": (case.summary or {}).get("two_axis_quadrant"),
        "created_at": case.created_at, "updated_at": case.updated_at,
    }


async def list_cases(db: AsyncSession, tenant_id: uuid.UUID, *, status: str | None = None, severity: str | None = None, provider_id: str | None = None, limit: int = 100, offset: int = 0) -> tuple[list[dict], int]:
    where = [Case.tenant_id == tenant_id]
    if status == "open":
        where.append(Case.status.in_(OPEN_STATUSES))
    elif status:
        where.append(Case.status == status)
    if severity:
        where.append(Case.severity == severity)
    if provider_id:
        where.append(Case.provider_id == provider_id)
    total = (await db.execute(select(func.count()).select_from(Case).where(*where))).scalar_one()
    rows = list((await db.execute(select(Case).where(*where).order_by(Case.risk_score.desc().nulls_last()).limit(limit).offset(offset))).scalars().all())
    users = await _users(db, tenant_id, {c.assigned_to for c in rows if c.assigned_to})
    providers = await provider_map(db, tenant_id, {c.provider_id for c in rows})
    return [summary(c, users.get(c.assigned_to), providers.get(c.provider_id)) for c in rows], total


# ---------- creation ----------

async def _next_case_id(db: AsyncSession, tenant_id: uuid.UUID) -> str:
    year = date.today().year
    prefix = f"CS-{year}-"
    existing = (await db.execute(select(Case.case_id).where(Case.tenant_id == tenant_id, Case.case_id.like(f"{prefix}%")))).scalars().all()
    highest = max((int(c[len(prefix):]) for c in existing if c[len(prefix):].isdigit()), default=0)
    return f"{prefix}{highest + 1:04d}"


async def upsert_for_claim(db: AsyncSession, tenant: Tenant, claim: Claim, result) -> Case:
    """Adds a routed claim to the provider's open case, or opens one. A case groups a provider's
    flagged claims so a reviewer sees the pattern rather than isolated alerts."""
    case = None
    if claim.case_ref:
        case = await db.get(Case, claim.case_ref)
    if case is None:
        case = (await db.execute(select(Case).where(Case.tenant_id == tenant.id, Case.provider_id == claim.provider_id, Case.status.in_(OPEN_STATUSES)).limit(1))).scalar_one_or_none()
    created = case is None
    if case is None:
        case = Case(tenant_id=tenant.id, case_id=await _next_case_id(db, tenant.id), provider_id=claim.provider_id, status="pending_review", primary_claim_id=claim.id)
        case.summary = {"opened_reason": getattr(result, "case_opening_reason", None), "opened_by_claim": claim.claim_id}
        db.add(case)
        await db.flush()
    claim.case_ref = case.id
    await db.flush()
    await refresh_aggregates(db, case)
    from app.services import similarity_service

    similarity_service.invalidate(tenant.id)  # the similar-case corpus now includes this claim
    if created:
        await AuditLogger(db).log("case.created", "case", case.case_id, tenant_id=tenant.id, details={"provider_id": case.provider_id, "risk_score": case.risk_score, "trigger_claim": claim.claim_id, "opened_reason": getattr(result, "case_opening_reason", None)})
        await event_bus.publish("case.created", {"tenant_id": str(tenant.id), "case_id": case.case_id, "provider_id": case.provider_id, "risk_score": case.risk_score})
    return case


async def refresh_aggregates(db: AsyncSession, case: Case) -> None:
    claims = await claims_of(db, case)
    if not claims:
        return
    top = claims[0]
    signals = [s for s in await signals_of(db, case) if s["detector"] != "similarity"]
    detectors = {s["detector"] for s in signals}
    case.primary_claim_id = top.id
    case.risk_score = top.risk_score
    case.suspicion_score = top.suspicion_score
    case.member_harm_score = max(c.member_harm_score or 0 for c in claims)
    case.evidence_strength = max(c.evidence_strength or 0 for c in claims)
    case.severity, case.priority_tier = top.severity, top.priority_tier
    case.expected_recovery = round(sum(float(c.total_billed or 0) for c in claims), 2)
    case.claim_count = len(claims)
    case.members_affected = len({c.member_id for c in claims if c.member_id})
    # Review effort grows with the number of distinct findings and, slowly, with claim volume.
    case.estimated_hours = min(16.0, round((2 + 0.75 * len(signals) + 0.5 * len(detectors) + 0.05 * len(claims)) * 2) / 2)
    case.summary = {
        "opened_reason": (case.summary or {}).get("opened_reason"),
        "opened_by_claim": (case.summary or {}).get("opened_by_claim"),
        # Name the case after its strongest checkable finding; a bare model score says little.
        "primary_flag": next((s["name"] for s in signals if s["detector"] != "ml"), signals[0]["name"] if signals else None),
        "two_axis_quadrant": top.two_axis_quadrant,
        "model_version": top.model_version,
        "signal_names": [s["name"] for s in signals],
    }
    await db.flush()


# ---------- views ----------

async def detail(db: AsyncSession, tenant: Tenant, case: Case) -> dict:
    claims = await claims_of(db, case)
    signals = await signals_of(db, case)
    provider = (await db.execute(select(Provider).where(Provider.tenant_id == tenant.id, Provider.provider_id == case.provider_id))).scalar_one_or_none()
    users = await _users(db, tenant.id, {case.assigned_to} if case.assigned_to else set())
    top = claims[0] if claims else None
    by_detector: dict[str, float] = {}
    for s in signals:
        by_detector[s["detector"]] = max(by_detector.get(s["detector"], 0.0), s["score"])
    return {
        **summary(case, users.get(case.assigned_to), (provider.name, provider.specialty) if provider else None),
        "provider": {"provider_id": case.provider_id, "name": provider.name if provider else None, "specialty": provider.specialty if provider else None, "on_provider_file": provider is not None},
        "suspicion_score": case.suspicion_score,
        "signal_breakdown": by_detector,
        "flags": [{"signal_id": s["signal_id"], "detector": s["detector"], "name": s["name"], "label": s["label"], "score": s["score"], "claim_id": s["claim_id"], "occurrences": s["occurrences"]} for s in signals],
        # Earlier claims from other cases that were billed alike and flagged for the same reasons.
        "similar_cases": [m for s in signals if s["detector"] == "similarity" for m in s["evidence"].get("similar_cases", []) if m.get("case_id") != case.case_id][:5],
        "member_harm_factors": (top.attributes or {}).get("_harm_factors", []) if top else [],
        "score_components": (top.attributes or {}).get("_components", {}) if top else {},
        "model_version": top.model_version if top else None,
        "model_warning": _model_warning(top.model_version if top else None),
        "primary_claim": {
            "claim_id": top.claim_id,
            "service_date": top.service_date,
            "total_billed": top.total_billed,
            "coverage_status": top.coverage_status,
            "lines": [{"line_id": l.line_id, "cpt_code": l.cpt_code, "units": l.units, "billed_amount": l.billed_amount} for l in top.lines],
        } if top else None,
        "claims": [{"claim_id": c.claim_id, "member_id": c.member_id, "service_date": c.service_date, "total_billed": c.total_billed, "risk_score": c.risk_score} for c in claims[:200]],
    }


async def case_limitations(db: AsyncSession, tenant: Tenant, case: Case, signals: list[dict]) -> list[str]:
    prior = (await db.execute(select(func.count()).select_from(Case).where(Case.tenant_id == tenant.id, Case.provider_id == case.provider_id, Case.id != case.id, Case.status.notin_(OPEN_STATUSES)))).scalar_one()
    known = (await db.execute(select(Provider.id).where(Provider.tenant_id == tenant.id, Provider.provider_id == case.provider_id))).first() is not None
    claims = await claims_of(db, case)
    degraded = any((c.model_version or "").startswith("fallback") for c in claims)
    history = (await db.execute(select(func.count()).select_from(Claim).where(Claim.tenant_id == tenant.id, Claim.provider_id == case.provider_id))).scalar_one()
    return build_limitations({s["name"] for s in signals}, provider_id=case.provider_id, ml_degraded=degraded, claim_count=case.claim_count, has_prior_outcome=prior > 0, provider_known=known, history_claims=history)


async def evidence(db: AsyncSession, tenant: Tenant, case: Case) -> dict:
    signals = await signals_of(db, case)
    return {
        "case_id": case.case_id,
        "model_warning": _model_warning((case.summary or {}).get("model_version")),
        "items": [
            {
                "signal_id": s["signal_id"], "detector": s["detector"], "name": s["name"], "title": s["label"], "summary": plain(s["name"]),
                "score_label": "confidence" if s["detector"] == "rule" else "similarity" if s["detector"] == "similarity" else "score", "score": s["score"], "severity": s["severity"],
                "evidence": s["evidence"], "source": {"claim_id": s["claim_id"], "fields": s["source_fields"]}, "occurrences": s["occurrences"],
            }
            for s in signals
        ],
        "limitations": await case_limitations(db, tenant, case, signals),
    }


async def timeline(db: AsyncSession, tenant: Tenant, case: Case) -> list[dict]:
    claims = await claims_of(db, case)
    events: list[dict] = []
    rows = await db.execute(
        select(DetectionSignal, Claim.claim_id, Claim.service_date)
        .join(Claim, Claim.id == DetectionSignal.claim_id)
        .where(DetectionSignal.tenant_id == tenant.id, Claim.case_ref == case.id)
        .order_by(Claim.service_date)
    )
    seen: set[str] = set()
    for s, claim_id, service_date in rows.all():
        name = s.rule_name or s.model_name or s.pattern_name or "unknown"
        if name in seen or service_date is None:
            continue
        seen.add(name)
        events.append({"date": service_date.isoformat(), "kind": s.detector, "title": f"{label(name)} first detected", "detail": f"Claim {claim_id}, {('confidence' if s.detector == 'rule' else 'score')} {s.score:.0%}"})
    refs = await db.execute(select(func.min(Referral.referral_date), func.count()).where(Referral.tenant_id == tenant.id, (Referral.from_provider_id == case.provider_id) | (Referral.to_provider_id == case.provider_id)))
    first_ref, n_refs = refs.one()
    if first_ref and n_refs:
        events.append({"date": first_ref.isoformat(), "kind": "graph", "title": "First referral involving this provider", "detail": f"{n_refs} referrals on record"})
    if claims:
        dates = [c.service_date for c in claims if c.service_date]
        if dates:
            events.append({"date": min(dates).isoformat(), "kind": "case", "title": "Earliest claim in this case", "detail": f"{len(claims)} claims between {min(dates)} and {max(dates)}"})
    events.append({"date": case.created_at.date().isoformat(), "kind": "case", "title": "Case opened for human review", "detail": "Routed to the SIU queue"})
    decisions = await db.execute(select(CaseDecision).where(CaseDecision.tenant_id == tenant.id, CaseDecision.case_id == case.id).order_by(CaseDecision.decided_at))
    for d in decisions.scalars():
        events.append({"date": d.decided_at.date().isoformat(), "kind": "case", "title": f"Decision recorded: {d.decision}", "detail": f"By {d.decided_by_label or 'reviewer'}"})
    return sorted(events, key=lambda e: e["date"])


async def network(db: AsyncSession, tenant: Tenant, case: Case, as_of: date | None = None) -> dict:
    signals = await signals_of(db, case)
    loop = next((s["evidence"].get("loop_members") for s in signals if s["name"] == "referral_loop" and s["evidence"].get("loop_members")), None) or []
    providers = list(dict.fromkeys([case.provider_id, *loop]))
    claim_rows = await db.execute(select(Claim.provider_id, Claim.member_id, Claim.facility_id, Claim.service_date, Claim.total_billed).where(Claim.tenant_id == tenant.id, Claim.provider_id.in_(providers)).limit(20_000))
    ref_rows = await db.execute(select(Referral.from_provider_id, Referral.to_provider_id, Referral.referral_date).where(Referral.tenant_id == tenant.id, Referral.from_provider_id.in_(providers) | Referral.to_provider_id.in_(providers)).limit(20_000))
    claims = [ClaimEdge(p, m, f, d, float(b or 0)) for p, m, f, d, b in claim_rows.all()]
    referrals = [ReferralEdge(a, b, d) for a, b, d in ref_rows.all()]
    data = export_graph(build_bipartite_graph(claims, referrals, as_of), in_loop=set(loop))
    dates = [c.service_date for c in claims if c.service_date] + [r.referral_date for r in referrals if r.referral_date]
    data.update(case_id=case.case_id, center_id=case.provider_id, loop_members=loop, range={"from": min(dates).isoformat() if dates else None, "to": max(dates).isoformat() if dates else None})
    return data


async def counterfactual(db: AsyncSession, tenant: Tenant, case: Case, only: list[str] | None = None, persist: bool = True) -> dict:
    signals = await signals_of(db, case)
    claims = await claims_of(db, case)
    top = claims[0] if claims else None
    objs = [Signal(s["detector"], s["name"], s["score"], s["confidence"]) for s in signals if s["detector"] != "similarity"]
    cfg = tenant.config or {}
    threshold = float((cfg.get("thresholds") or {}).get("routing", 0.7))
    harm = case.member_harm_score or 0.0
    result = cf.generate(objs, dollar_impact(top.total_billed if top else 0), harm, threshold, cfg.get("weights"), only)
    result["case_id"] = case.case_id
    if persist:
        for s in result["scenarios"]:
            db.add(Counterfactual(tenant_id=tenant.id, case_id=case.id, scenario=s["scenario"], original_risk=s["original_risk"], counterfactual_risk=s["counterfactual_risk"], conditions={"removes": s["removes"]}))
        await db.flush()
    return result


# ---------- actions ----------

async def set_status(db: AsyncSession, case: Case, status: str, principal: Principal, request=None) -> Case:
    """Moves a case between working states. Outcomes (confirmed, false positive, escalated) can
    only be set by recording a decision, so every outcome carries a reviewer and their reasoning."""
    if status not in WORKFLOW_STATUSES:
        raise ValidationFailed(f"'{status}' is an outcome, not a working status. Record a decision on the case to set it.", allowed=list(WORKFLOW_STATUSES))
    if case.status not in WORKFLOW_STATUSES:
        raise ValidationFailed("This case already has a recorded outcome. Record a new decision to change it.")
    before, case.status = case.status, status
    await AuditLogger(db).log("case.status_changed", "case", case.case_id, principal=principal, details={"from": before, "to": status}, request=request)
    await db.flush()
    return case


async def assign(db: AsyncSession, tenant: Tenant, case: Case, assignee_external_id: str, principal: Principal, request=None) -> Case:
    user = await tenant_service.require_user(db, tenant.id, assignee_external_id)
    case.assigned_to = user.id
    if case.status == "pending_review":
        case.status = "in_review"
    await AuditLogger(db).log("case.assigned", "case", case.case_id, principal=principal, details={"assigned_to": assignee_external_id}, request=request)
    await db.flush()
    return case


async def decide(db: AsyncSession, tenant: Tenant, case: Case, body: DecisionIn, principal: Principal, request=None) -> dict:
    """Records a reviewer's decision. The effects are limited to this system: the case status, a
    training label and audit entries. Nothing is sent to the claims platform or the provider."""
    claims = await claims_of(db, case)
    known_lines = {l.line_id for c in claims for l in c.lines}
    unknown = [d.line_id for d in body.line_decisions if d.line_id not in known_lines]
    if unknown:
        raise ValidationFailed("Some line IDs do not belong to this case.", unknown_line_ids=unknown)

    if body.decision == "reassign":
        if not body.assignee:
            raise ValidationFailed("Choose who to reassign the case to.", field="assignee")
        user = await tenant_service.require_user(db, tenant.id, body.assignee)
        case.assigned_to = user.id

    count = (await db.execute(select(func.count()).select_from(CaseDecision).where(CaseDecision.tenant_id == tenant.id))).scalar_one()
    final_label = DECISION_LABEL[body.decision]
    decision = CaseDecision(
        tenant_id=tenant.id, decision_id=f"DEC-{utcnow().year}-{count + 1:05d}", case_id=case.id, decision=body.decision, final_label=final_label,
        notes=body.notes, line_decisions=[d.model_dump() for d in body.line_decisions], next_action=body.next_action,
        decided_by=principal.user_id, decided_by_label=principal.subject,
    )
    db.add(decision)
    case.status = "escalated" if body.decision == "confirm_fraud" and (body.next_action or "").startswith("escalate") else DECISION_STATUS[body.decision]

    training_queued = False
    if final_label is not None and claims:
        top = claims[0]
        xgb = (await db.execute(select(DetectionSignal.score).where(DetectionSignal.tenant_id == tenant.id, DetectionSignal.claim_id == top.id, DetectionSignal.model_name == "xgboost"))).scalar_one_or_none()
        fb_count = (await db.execute(select(func.count()).select_from(ModelFeedback).where(ModelFeedback.tenant_id == tenant.id))).scalar_one()
        db.add(
            ModelFeedback(
                tenant_id=tenant.id, feedback_id=f"FB-{utcnow().year}-{fb_count + 1:05d}", claim_id=top.id, case_id=case.id, model_version=top.model_version,
                fraud_probability=xgb, risk_score=top.risk_score, human_decision=body.decision, final_label=final_label,
                reviewer_id=principal.user_id, reviewer_label=principal.subject, notes=body.notes, features=(top.attributes or {}).get("_features"),
            )
        )
        training_queued = True

    audit = AuditLogger(db)
    for d in body.line_decisions:
        await audit.log("case.line_decision", "case", case.case_id, principal=principal, details={"line_id": d.line_id, "decision": d.decision}, request=request)
    await audit.log("case.decision", "case", case.case_id, principal=principal, details={"decision": body.decision, "next_action": body.next_action, "decision_id": decision.decision_id, "final_label": final_label}, request=request)
    await db.flush()
    from app.services import similarity_service

    similarity_service.invalidate(tenant.id)  # the case's outcome is part of what similar-case results show
    await event_bus.publish("case.decided", {"tenant_id": str(tenant.id), "case_id": case.case_id, "decision": body.decision})
    return {
        "decision_id": decision.decision_id, "case_id": case.case_id, "decision": body.decision, "final_label": final_label,
        "decided_at": decision.decided_at, "decided_by": principal.subject, "status": case.status,
        "training_queued": training_queued, "audit_logged": True, "next_action": body.next_action,
    }
