"""Plain data objects the detectors work on. Detectors never touch the database: the pipeline
loads a DetectionContext once per claim, which keeps every rule a pure, unit-testable function and
lets the training scripts reuse exactly the same code on synthetic data."""
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class LineData:
    line_id: str
    cpt_code: str | None = None
    modifiers: list[str] = field(default_factory=list)
    units: int = 1
    billed_amount: float = 0.0
    paid_amount: float = 0.0
    service_date: date | None = None
    diagnosis_pointer: list[int] = field(default_factory=list)


@dataclass
class ClaimData:
    claim_id: str
    member_id: str | None = None
    provider_id: str | None = None
    facility_id: str | None = None
    referring_provider_id: str | None = None
    service_date: date | None = None
    claim_type: str | None = "professional"
    total_billed: float = 0.0
    total_paid: float = 0.0
    diagnosis_codes: list[str] = field(default_factory=list)
    lines: list[LineData] = field(default_factory=list)
    plan_type: str | None = None
    policy_start_date: date | None = None
    pre_auth_number: str | None = None
    member_age: int | None = None
    attributes: dict = field(default_factory=dict)

    @property
    def cpt_codes(self) -> list[str]:
        return [l.cpt_code for l in self.lines if l.cpt_code]


@dataclass
class ProviderInfo:
    provider_id: str | None
    known: bool = False
    specialty: str | None = None
    license_status: str = "active"
    active: bool = True
    address: str | None = None
    city: str | None = None
    owner_id: str | None = None


@dataclass
class MemberInfo:
    member_id: str | None
    known: bool = False
    age: int | None = None
    low_income_area: bool = False
    eligibility_end: date | None = None


@dataclass
class PeerStats:
    avg_claim: float = 1400.0
    level5_rate: float = 0.12
    visits_per_member: float = 2.0


@dataclass
class AmountStats:
    """Typical billed amount for one unit of a procedure code in the tenant's own recent claims."""
    typical: float  # median billed amount per unit
    lines: int  # service lines the median was taken over


@dataclass
class ProviderVolume:
    """One provider's activity over the prior 90 days, used to compare a provider with its peers."""
    provider_id: str
    claims: int = 0
    members: int = 0
    billed: float = 0.0
    lines: int = 0
    bypass_lines: int = 0  # lines carrying a distinct-service (bypass) modifier


@dataclass
class Signal:
    detector: str  # rule | ml | graph | temporal
    name: str
    score: float
    confidence: float | None = None
    severity: str = "medium"
    evidence: dict = field(default_factory=dict)
    source_fields: list[str] = field(default_factory=list)


@dataclass
class DetectionContext:
    claim: ClaimData
    provider: ProviderInfo
    member: MemberInfo
    provider_history: list[ClaimData] = field(default_factory=list)  # same provider, prior 90 days, excluding this claim
    member_history: list[ClaimData] = field(default_factory=list)  # same member, prior 90 days, excluding this claim
    peers: PeerStats = field(default_factory=PeerStats)
    referral_edges: list[tuple[str, str]] = field(default_factory=list)  # (from_provider, to_provider)
    facility_locations: dict[str, tuple[float, float, str]] = field(default_factory=dict)  # facility_id -> lat, lng, city
    provider_master_loaded: bool = False
    member_master_loaded: bool = False
    # Closed referral loop this provider belongs to, found by the graph detector before rules run.
    referral_loop: list[str] | None = None
    referral_loop_count: int = 0
    # Tenant history per procedure code on this claim, prior 90 days. Empty for codes never seen.
    typical_amounts: dict[str, AmountStats] = field(default_factory=dict)
    # Other providers in the same specialty, prior 90 days. Empty when the specialty is unknown.
    specialty_peers: list[ProviderVolume] = field(default_factory=list)
    # Earliest service date on record for this provider and for the tenant as a whole.
    provider_first_seen: date | None = None
    tenant_first_seen: date | None = None

    def provider_window(self, days: int) -> list[ClaimData]:
        d = self.claim.service_date
        if d is None:
            return []
        start = d - timedelta(days=days)
        return [c for c in self.provider_history if c.service_date and start <= c.service_date <= d]

    def member_window(self, days: int) -> list[ClaimData]:
        d = self.claim.service_date
        if d is None:
            return []
        start = d - timedelta(days=days)
        return [c for c in self.member_history if c.service_date and start <= c.service_date <= d]


def severity_for(score: float) -> str:
    if score >= 0.8:
        return "critical"
    if score >= 0.6:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"
