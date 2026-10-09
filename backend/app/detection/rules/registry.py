from app.core.logging import logger
from app.detection.context import DetectionContext, Signal
from app.detection.rules.amount_outlier import AmountOutlier
from app.detection.rules.base import Rule
from app.detection.rules.coding_validity import CodingValidity
from app.detection.rules.demographic_mismatch import DemographicMismatch
from app.detection.rules.diagnosis_procedure_mismatch import DiagnosisProcedureMismatch
from app.detection.rules.duplicate_billing import DuplicateBilling
from app.detection.rules.excessive_utilization import ExcessiveUtilization
from app.detection.rules.impossible_timing import ImpossibleTiming
from app.detection.rules.member_eligibility import MemberEligibility
from app.detection.rules.modifier_overuse import ModifierOveruse
from app.detection.rules.ncci_edits import NCCIEdits
from app.detection.rules.new_provider_burst import NewProviderBurst
from app.detection.rules.peer_outlier import PeerOutlier
from app.detection.rules.phantom_services import PhantomServices
from app.detection.rules.provider_shopping import ProviderShopping
from app.detection.rules.provider_validity import ProviderValidity
from app.detection.rules.referral_loops import ReciprocalReferrals
from app.detection.rules.split_billing import SplitBilling
from app.detection.rules.unbundling import Unbundling
from app.detection.rules.units_cap import UnitsCap
from app.detection.rules.upcoding import Upcoding

ALL_RULES: list[Rule] = [
    DuplicateBilling(),
    Upcoding(),
    Unbundling(),
    NCCIEdits(),
    PhantomServices(),
    ExcessiveUtilization(),
    ImpossibleTiming(),
    ReciprocalReferrals(),
    CodingValidity(),
    ProviderValidity(),
    MemberEligibility(),
    UnitsCap(),
    AmountOutlier(),
    DiagnosisProcedureMismatch(),
    DemographicMismatch(),
    PeerOutlier(),
    SplitBilling(),
    ModifierOveruse(),
    NewProviderBurst(),
    ProviderShopping(),
]


class RuleEngine:
    def __init__(self, rules: list[Rule] | None = None, disabled: set[str] | None = None):
        self.rules = rules if rules is not None else ALL_RULES
        self.disabled = disabled or set()

    def run_all(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        for rule in self.rules:
            if rule.name in self.disabled:
                continue
            try:
                signal = rule.evaluate(ctx)
            except Exception as exc:  # noqa: BLE001  One faulty rule must not stop the others.
                logger.error("rule_error", rule=rule.name, claim_id=ctx.claim.claim_id, error=str(exc))
                continue
            if signal is not None:
                signals.append(signal)
        return signals

    def catalogue(self) -> list[dict]:
        return [{"name": r.name, "description": r.description, "enabled": r.name not in self.disabled} for r in self.rules]
