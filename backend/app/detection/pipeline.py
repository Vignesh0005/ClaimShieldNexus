import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from sqlalchemy import String, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import metrics, perf
from app.core.cache import cache
from app.core.logging import logger
from app.db.base import utcnow
from app.detection.context import AmountStats, ClaimData, DetectionContext, LineData, MemberInfo, PeerStats, ProviderInfo, ProviderVolume, Signal
from app.detection.coverage.engine import CoverageResult, CoverageRulesEngine, input_from_claim
from app.detection.coverage.loader import CoverageRuleLoader
from app.detection.graph.builder import ReferralEdge
from app.detection.graph.engine import GraphEngine, LoopStats
from app.detection.ml.registry import FALLBACK_VERSION, MLEngine
from app.detection.ml.training import SYNTHETIC_WARNING
from app.detection.rules.registry import RuleEngine
from app.detection.scoring.fusion import RiskFusion, RiskResult
from app.detection.temporal.spikes import billing_spike
from app.models import Claim, ClaimLineItem, CoverageRule, DetectionSignal, Facility, Member, Provider, Referral, Tenant
from app.utils.codes import EM_CODES, EM_HIGH_LEVEL, NCCI_BYPASS_MODIFIERS

HISTORY_DAYS = 90
ALL_STAGES = frozenset({"coverage", "rules", "ml", "graph", "temporal"})


def claim_to_data(row: Claim) -> ClaimData:
    return ClaimData(
        claim_id=row.claim_id,
        member_id=row.member_id,
        provider_id=row.provider_id,
        facility_id=row.facility_id,
        referring_provider_id=row.referring_provider_id,
        service_date=row.service_date,
        claim_type=row.claim_type,
        total_billed=float(row.total_billed or 0),
        total_paid=float(row.total_paid or 0),
        diagnosis_codes=list(row.diagnosis_codes or []),
        lines=[
            LineData(l.line_id, l.cpt_code, list(l.modifiers or []), l.units or 1, float(l.billed_amount or 0), float(l.paid_amount or 0), l.service_date, list(l.diagnosis_pointer or []))
            for l in row.lines
        ],
        plan_type=row.plan_type,
        policy_start_date=row.policy_start_date,
        pre_auth_number=row.pre_auth_number,
        member_age=row.member_age,
        attributes=dict(row.attributes or {}),
    )


def serialize_signal(signal_id: str, s: Signal) -> dict:
    """API shape for a signal; the keys depend on which detector produced it."""
    base = {"signal_id": signal_id, "detector": s.detector, "severity": s.severity}
    if s.detector == "rule":
        return {**base, "rule_name": s.name, "confidence": s.confidence, "evidence": s.evidence, "source_fields": s.source_fields}
    if s.detector == "ml":
        return {**base, "model": s.evidence.get("model", s.name), "detector_name": s.name, "score": s.score, "top_features": s.evidence.get("top_features", []), "evidence": s.evidence}
    return {**base, "pattern": s.name, "score": s.score, "evidence": s.evidence, "source_fields": s.source_fields}


@dataclass
class DetectionResult:
    claim_id: str
    coverage: CoverageResult
    signals: list[Signal] = field(default_factory=list)
    risk: RiskResult | None = None
    model_version: str | None = None
    ml_degraded: bool = False
    features: dict = field(default_factory=dict)
    processing_time_ms: int = 0
    case_id: str | None = None
    case_opening_reason: str | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "claim_id": self.claim_id,
            "coverage_status": self.coverage.overall_status,
            "fwa_signals": [serialize_signal(f"SIG-{i + 1:03d}", s) for i, s in enumerate(self.signals)],
            "risk_score": None,
            "not_fraud": True if self.risk is None else None,
            "review_required": self.coverage.review_required,
            "review_reasons": self.coverage.review_reasons,
            "model_version": self.model_version,
            "model_warning": SYNTHETIC_WARNING if self.model_version and not self.model_version.startswith("fallback") else None,
            "ml_degraded": self.ml_degraded,
            "case_id": self.case_id,
            "case_opening_reason": self.case_opening_reason,
            "processing_time_ms": self.processing_time_ms,
        }
        if self.risk is None:
            out["not_denial"] = True
            out["message"] = "Coverage needs human review. FWA detection was not run and no fraud score was produced."
        else:
            out.pop("not_fraud")
            r = self.risk
            out.update(
                risk_score=r.risk_score,
                composite_risk=r.composite_risk,
                max_rule_confidence=r.max_rule_confidence,
                suspicion_score=r.suspicion_score,
                evidence_strength=r.evidence_strength,
                two_axis_quadrant=r.two_axis_quadrant,
                member_harm_score=r.member_harm_score,
                severity=r.severity,
                priority_tier=r.priority_tier,
                score_components=r.components,
            )
        return out


async def coverage_rules(db: AsyncSession):
    """Rules from the coverage_rules table when it has been seeded, else the bundled JSON."""
    rows = (await db.execute(select(CoverageRule))).scalars().all()
    return CoverageRuleLoader.from_rows(rows) if rows else CoverageRuleLoader().load_all()


class DetectionPipeline:
    """Coverage rules, then FWA rules, ML, graph and temporal detectors, then risk fusion.

    The pipeline only scores and explains. Its strongest effect is creating a case for a person to
    review; it never denies, pends or adjusts a claim."""

    def __init__(self, db: AsyncSession, tenant: Tenant):
        self.db, self.tenant = db, tenant
        cfg = tenant.config or {}
        self.settings = get_settings()
        self.rule_engine = RuleEngine(disabled=set(cfg.get("disabled_rules", [])))
        self.ml_engine = MLEngine()
        self.graph_engine = GraphEngine()
        self.fusion = RiskFusion(thresholds=cfg.get("thresholds"), weights=cfg.get("weights"))
        self.case_threshold = float((cfg.get("thresholds") or {}).get("routing", self.settings.case_risk_threshold))
        opening = cfg.get("case_opening") or {}
        self.tier2_enabled = bool(opening.get("tier2_enabled", True))
        self.tier2_rule_threshold = float(opening.get("tier2_rule_threshold", 0.90))
        self.tier3_enabled = bool(opening.get("tier3_enabled", True))

    def case_opening_reason(self, result: "DetectionResult") -> str | None:
        """Why a claim is sent to a reviewer, or None if it is not. Opening a case only asks a
        person to look; it decides nothing about the claim.

        Tier 1: risk score at or above the tenant's routing threshold (default 0.70).
        Tier 2: any single rule finding at or above tier2_rule_threshold (default 0.90).
        Tier 3: the claim sits in the "siu" quadrant (high suspicion and strong evidence).
        Tiers 2 and 3 can be switched off per tenant in config["case_opening"]."""
        r = result.risk
        if r is None:
            return None
        if r.risk_score >= self.case_threshold:
            return "tier1_risk_score"
        if self.tier2_enabled and r.max_rule_confidence >= self.tier2_rule_threshold:
            return "tier2_rule_confidence"
        if self.tier3_enabled and r.two_axis_quadrant == "siu":
            return "tier3_siu_quadrant"
        return None

    # ---------- context loading ----------

    async def _history(self, column, value: str | None, claim: Claim) -> list[ClaimData]:
        if not value or claim.service_date is None:
            return []
        stmt = (
            select(Claim)
            .where(
                Claim.tenant_id == self.tenant.id,
                column == value,
                Claim.id != claim.id,
                Claim.service_date >= claim.service_date - timedelta(days=HISTORY_DAYS),
                Claim.service_date <= claim.service_date,
            )
            .order_by(Claim.service_date.desc())
            .limit(2000)
        )
        return [claim_to_data(c) for c in (await self.db.execute(stmt)).scalars().all()]

    async def _peers(self, specialty: str | None, as_of: date | None) -> PeerStats:
        key = f"peers:{self.tenant.id}:{specialty or '*'}"
        cached = await cache.get(key)
        if cached:
            return PeerStats(**cached)
        t, since = self.tenant.id, (as_of or date.today()) - timedelta(days=HISTORY_DAYS)
        claims = select(Claim.id, Claim.total_billed, Claim.member_id, Claim.provider_id).where(Claim.tenant_id == t, Claim.service_date >= since)
        if specialty:
            claims = claims.where(Claim.provider_id.in_(select(Provider.provider_id).where(Provider.tenant_id == t, Provider.specialty == specialty)))
        sub = claims.subquery()
        avg, n, pairs = (await self.db.execute(select(func.avg(sub.c.total_billed), func.count(), func.count(func.distinct(sub.c.member_id + "|" + sub.c.provider_id))))).one()
        stats = PeerStats()
        if n and n >= 30:  # with fewer claims the defaults are a better guide than a noisy sample
            em = select(ClaimLineItem.cpt_code, func.count()).where(ClaimLineItem.tenant_id == t, ClaimLineItem.claim_id.in_(select(sub.c.id)), ClaimLineItem.cpt_code.in_(EM_CODES)).group_by(ClaimLineItem.cpt_code)
            counts = dict((await self.db.execute(em)).all())
            total_em = sum(counts.values())
            stats = PeerStats(
                avg_claim=float(avg or stats.avg_claim),
                level5_rate=sum(counts.get(c, 0) for c in EM_HIGH_LEVEL) / total_em if total_em >= 20 else stats.level5_rate,
                # Visits per member-provider pair over 90 days, scaled to 30.
                visits_per_member=max(1.0, (n / max(pairs, 1)) / 3),
            )
        await cache.set(key, stats.__dict__, ttl=300)
        return stats

    async def _typical_amounts(self, claim: Claim, data: ClaimData) -> dict[str, AmountStats]:
        """Median billed amount per unit for each procedure code on the claim, from this tenant's
        other claims in the prior 90 days. Cached per code, so most claims add no query."""
        out: dict[str, AmountStats] = {}
        as_of = claim.service_date or date.today()
        for code in set(data.cpt_codes):
            key = f"amount:{self.tenant.id}:{code}"
            cached = await cache.get(key)
            if cached is None:
                rows = await self.db.execute(
                    select(ClaimLineItem.billed_amount, ClaimLineItem.units)
                    .where(ClaimLineItem.tenant_id == self.tenant.id, ClaimLineItem.cpt_code == code, ClaimLineItem.claim_id != claim.id, ClaimLineItem.billed_amount > 0, ClaimLineItem.service_date >= as_of - timedelta(days=HISTORY_DAYS), ClaimLineItem.service_date <= as_of)
                    .order_by(ClaimLineItem.service_date.desc())
                    .limit(1000)
                )
                per_unit = [float(amount) / max(units or 1, 1) for amount, units in rows.all()]
                cached = {"typical": median(per_unit) if per_unit else 0.0, "lines": len(per_unit)}
                await cache.set(key, cached, ttl=300)
            if cached["lines"]:
                out[code] = AmountStats(**cached)
        return out

    async def _specialty_peers(self, specialty: str | None, as_of: date | None) -> list[ProviderVolume]:
        """Claims, members, billed amount and modifier use per provider in one specialty over the
        prior 90 days. Cached per specialty, so most claims add no query."""
        if not specialty:
            return []
        key = f"peer-providers:{self.tenant.id}:{specialty}"
        cached = await cache.get(key)
        if cached is None:
            t, until = self.tenant.id, as_of or date.today()
            where = (
                Claim.tenant_id == t, Claim.service_date >= until - timedelta(days=HISTORY_DAYS), Claim.service_date <= until,
                Claim.provider_id.in_(select(Provider.provider_id).where(Provider.tenant_id == t, Provider.specialty == specialty)),
            )
            volumes = await self.db.execute(select(Claim.provider_id, func.count(), func.count(func.distinct(Claim.member_id)), func.coalesce(func.sum(Claim.total_billed), 0)).where(*where).group_by(Claim.provider_id))
            peers = {pid: {"provider_id": pid, "claims": int(n), "members": int(members), "billed": float(billed), "lines": 0, "bypass_lines": 0} for pid, n, members, billed in volumes.all()}
            line_counts = await self.db.execute(select(Claim.provider_id, func.count()).join(ClaimLineItem, ClaimLineItem.claim_id == Claim.id).where(*where, ClaimLineItem.cpt_code.isnot(None)).group_by(Claim.provider_id))
            for pid, n in line_counts.all():
                peers[pid]["lines"] = int(n)
            # Modifiers are a JSON list, so lines that carry any are fetched and counted here.
            with_modifiers = await self.db.execute(
                select(Claim.provider_id, ClaimLineItem.modifiers).join(ClaimLineItem, ClaimLineItem.claim_id == Claim.id)
                .where(*where, ClaimLineItem.cpt_code.isnot(None), cast(ClaimLineItem.modifiers, String).notin_(("[]", "null"))).limit(20_000)
            )
            for pid, modifiers in with_modifiers.all():
                if set(modifiers or []) & NCCI_BYPASS_MODIFIERS:
                    peers[pid]["bypass_lines"] += 1
            cached = list(peers.values())
            await cache.set(key, cached, ttl=300)
        return [ProviderVolume(**p) for p in cached]

    async def _first_seen(self, claim: Claim, provider_history: list[ClaimData]) -> tuple[date | None, date | None]:
        """Earliest service date on record for the claim's provider and for the tenant."""
        if claim.service_date is None or not claim.provider_id:
            return None, None
        t = self.tenant.id
        key = f"tenant-first-seen:{t}"
        tenant_first = await cache.get(key)
        if tenant_first is None:
            found = (await self.db.execute(select(func.min(Claim.service_date)).where(Claim.tenant_id == t))).scalar_one_or_none()
            tenant_first = str(found or claim.service_date)
            await cache.set(key, tenant_first, ttl=3600)
        tenant_first = min(date.fromisoformat(tenant_first), claim.service_date)
        earliest = min((c.service_date for c in provider_history if c.service_date), default=claim.service_date)
        if (claim.service_date - earliest).days > 30:
            return earliest, tenant_first  # plainly not a new provider; the exact date does not matter
        found = (await self.db.execute(select(func.min(Claim.service_date)).where(Claim.tenant_id == t, Claim.provider_id == claim.provider_id))).scalar_one_or_none()
        return min(found or earliest, earliest), tenant_first

    async def load_context(self, claim: Claim, data: ClaimData | None = None) -> DetectionContext:
        t = self.tenant.id
        data = data or claim_to_data(claim)
        provider_row = (await self.db.execute(select(Provider).where(Provider.tenant_id == t, Provider.provider_id == claim.provider_id))).scalar_one_or_none()
        member_row = (await self.db.execute(select(Member).where(Member.tenant_id == t, Member.member_id == claim.member_id))).scalar_one_or_none()
        provider_master = provider_row is not None or (await self.db.execute(select(Provider.id).where(Provider.tenant_id == t).limit(1))).first() is not None
        member_master = member_row is not None or (await self.db.execute(select(Member.id).where(Member.tenant_id == t).limit(1))).first() is not None

        provider = ProviderInfo(claim.provider_id)
        if provider_row:
            provider = ProviderInfo(claim.provider_id, True, provider_row.specialty, provider_row.license_status, provider_row.active, provider_row.address, provider_row.city, provider_row.owner_id)
        member = MemberInfo(claim.member_id)
        if member_row:
            member = MemberInfo(claim.member_id, True, member_row.age, member_row.low_income_area, member_row.eligibility_end)

        provider_history = await self._history(Claim.provider_id, claim.provider_id, claim)
        member_history = await self._history(Claim.member_id, claim.member_id, claim)

        pair = [p for p in (claim.provider_id, claim.referring_provider_id) if p]
        edges: list[tuple[str, str]] = []
        if len(pair) == 2:
            rows = await self.db.execute(select(Referral.from_provider_id, Referral.to_provider_id).where(Referral.tenant_id == t, Referral.from_provider_id.in_(pair), Referral.to_provider_id.in_(pair), Referral.claim_id.is_(None) | (Referral.claim_id != claim.claim_id)))
            edges = [(a, b) for a, b in rows.all()]

        facility_ids = {c.facility_id for c in member_history + [data] if c.facility_id}
        locations: dict[str, tuple[float, float, str]] = {}
        if len(facility_ids) > 1:
            rows = await self.db.execute(select(Facility).where(Facility.tenant_id == t, Facility.facility_id.in_(facility_ids)))
            locations = {f.facility_id: (f.lat, f.lng, f.city or f.facility_id) for f in rows.scalars() if f.lat is not None and f.lng is not None}

        provider_first_seen, tenant_first_seen = await self._first_seen(claim, provider_history)
        return DetectionContext(
            claim=data, provider=provider, member=member, provider_history=provider_history, member_history=member_history,
            peers=await self._peers(provider.specialty, claim.service_date), referral_edges=edges, facility_locations=locations,
            provider_master_loaded=provider_master, member_master_loaded=member_master,
            typical_amounts=await self._typical_amounts(claim, data),
            specialty_peers=await self._specialty_peers(provider.specialty, claim.service_date),
            provider_first_seen=provider_first_seen, tenant_first_seen=tenant_first_seen,
        )

    # ---------- graph ----------

    async def _find_loop(self, ctx: DetectionContext):
        """Looks for a closed referral loop containing the claim's provider. Returns the loop and
        claim totals for its providers, and records the loop on the context for the rule engine."""
        t, pid = self.tenant.id, ctx.claim.provider_id
        if not pid:
            return None, None
        loop = None
        involved = (await self.db.execute(select(Referral.id).where(Referral.tenant_id == t, (Referral.from_provider_id == pid) | (Referral.to_provider_id == pid)).limit(1))).first()
        stats = None
        if involved:
            since = (ctx.claim.service_date or date.today()) - timedelta(days=365)
            rows = await self.db.execute(select(Referral.from_provider_id, Referral.to_provider_id, Referral.referral_date).where(Referral.tenant_id == t, Referral.referral_date >= since).limit(50_000))
            loop = self.graph_engine.find_loop(pid, [ReferralEdge(a, b, d) for a, b, d in rows.all()])
            if loop:
                agg = await self.db.execute(select(func.count(), func.coalesce(func.sum(Claim.total_billed), 0)).where(Claim.tenant_id == t, Claim.provider_id.in_(loop.providers), Claim.service_date >= since))
                n, dollars = agg.one()
                members = await self.db.execute(select(Claim.member_id).where(Claim.tenant_id == t, Claim.provider_id.in_(loop.providers), Claim.service_date >= since).distinct().limit(10_000))
                stats = LoopStats(int(n), float(dollars), {m for (m,) in members.all() if m})
                ctx.referral_loop, ctx.referral_loop_count = loop.providers, loop.referrals
        return loop, stats

    async def _graph_signals(self, ctx: DetectionContext, loop, stats) -> list[Signal]:
        t, pid = self.tenant.id, ctx.claim.provider_id
        if not pid:
            return []
        addresses: dict[str, str | None] = {}
        if ctx.provider.address:
            rows = await self.db.execute(select(Provider.provider_id, Provider.address).where(Provider.tenant_id == t, Provider.address == ctx.provider.address).limit(200))
            addresses = dict(rows.all())
        owners: dict[str, str | None] = {}
        if loop:
            rows = await self.db.execute(select(Provider.provider_id, Provider.owner_id).where(Provider.tenant_id == t, Provider.provider_id.in_(loop.providers)))
            owners = dict(rows.all())
        return self.graph_engine.signals(pid, loop, stats, addresses, owners)

    # ---------- run ----------

    async def evaluate(self, claim: Claim, stages: frozenset[str] = ALL_STAGES) -> DetectionResult:
        """Runs the requested stages and returns the result without writing anything."""
        started = time.perf_counter()
        data = claim_to_data(claim)
        engine = CoverageRulesEngine(await coverage_rules(self.db))
        coverage = engine.evaluate(input_from_claim(data))
        result = DetectionResult(claim_id=claim.claim_id, coverage=coverage)

        # Coverage failure is not fraud and not a denial: stop here and ask for human review.
        if "coverage" in stages and coverage.blocks_detection:
            result.processing_time_ms = int((time.perf_counter() - started) * 1000)
            return result

        ctx = await self.load_context(claim, data)
        signals: list[Signal] = []
        loop = stats = None
        if self.settings.enable_graph_analytics and stages & {"rules", "graph"}:
            loop, stats = await self._find_loop(ctx)
        if "rules" in stages:
            signals += self.rule_engine.run_all(ctx)
        if "ml" in stages:
            ml_signals, result.features, prediction = await self.ml_engine.run_all(ctx)
            signals += ml_signals
            result.model_version = prediction.model_version
            result.ml_degraded = prediction.degraded or prediction.fraud_probability is None
            if result.ml_degraded:
                metrics.ml_degraded.inc()
        if "graph" in stages and self.settings.enable_graph_analytics:
            signals += await self._graph_signals(ctx, loop, stats)
        if "temporal" in stages and self.settings.enable_temporal_analytics:
            spike = billing_spike(ctx)
            if spike:
                signals.append(spike)

        # Similar earlier claims: reviewer context, retrieved only for claims that were flagged.
        flagged = [s.name for s in signals if s.name != "coding_validity"]
        if flagged and "ml" in stages and self.settings.enable_similarity:
            from app.services import similarity_service

            matches = await similarity_service.similar_to_claim(self.db, self.tenant, data, [s.name for s in signals])
            if matches:
                signals.append(
                    Signal(
                        "similarity", "similar_cases", matches[0]["similarity"], severity="low",
                        evidence={"similar_cases": matches, "method": "TF-IDF cosine similarity over procedure codes, diagnosis codes and finding names", "corpus": similarity_service.corpus_mode(self.tenant), "note": "Context only. Not used in the risk score."},
                        source_fields=["lines.cpt_code", "diagnosis_codes"],
                    )
                )

        result.signals = sorted(signals, key=lambda s: (s.detector != "similarity", s.score), reverse=True)
        result.risk = self.fusion.fuse(ctx, result.signals)
        result.model_version = result.model_version or FALLBACK_VERSION
        result.processing_time_ms = int((time.perf_counter() - started) * 1000)
        return result

    async def run(self, claim: Claim) -> DetectionResult:
        """Full pipeline with persistence: stores signals and scores, and opens or updates a case
        when the risk score reaches the tenant's routing threshold."""
        from app.services import case_service

        result = await self.evaluate(claim)
        t = self.tenant.id
        await self.db.execute(delete(DetectionSignal).where(DetectionSignal.tenant_id == t, DetectionSignal.claim_id == claim.id))
        for i, s in enumerate(result.signals):
            self.db.add(
                DetectionSignal(
                    tenant_id=t, claim_id=claim.id, signal_id=f"SIG-{i + 1:03d}", detector=s.detector,
                    rule_name=s.name if s.detector == "rule" else None,
                    model_name=s.name if s.detector == "ml" else None,
                    pattern_name=s.name if s.detector in ("graph", "temporal", "similarity") else None,
                    confidence=s.confidence, score=s.score, severity=s.severity, evidence=s.evidence, source_fields=s.source_fields,
                )
            )
        claim.coverage_status = result.coverage.overall_status
        claim.coverage_details = result.coverage.to_dict()
        r = result.risk
        claim.risk_score = r.risk_score if r else None
        claim.suspicion_score = r.suspicion_score if r else None
        claim.evidence_strength = r.evidence_strength if r else None
        claim.member_harm_score = r.member_harm_score if r else None
        claim.severity = r.severity if r else None
        claim.priority_tier = r.priority_tier if r else None
        claim.two_axis_quadrant = r.two_axis_quadrant if r else None
        claim.model_version = result.model_version
        claim.attributes = {**(claim.attributes or {}), "_features": result.features, "_harm_factors": r.harm_factors if r else [], "_components": r.components if r else {}}
        claim.processing_status = "processed"
        claim.processing_error = None
        claim.processing_time_ms = result.processing_time_ms
        claim.processed_at = utcnow()
        await self.db.flush()

        result.case_opening_reason = self.case_opening_reason(result)
        if result.case_opening_reason:
            case = await case_service.upsert_for_claim(self.db, self.tenant, claim, result)
            result.case_id = case.case_id

        metrics.detection_latency.observe(result.processing_time_ms / 1000)
        perf.record(result.processing_time_ms)
        metrics.claims_processed.labels(str(t), "coverage_review" if r is None else r.severity).inc()
        logger.info("claim_processed", claim_id=claim.claim_id, coverage=claim.coverage_status, risk=claim.risk_score, signals=len(result.signals), ms=result.processing_time_ms, case=result.case_id)
        return result
