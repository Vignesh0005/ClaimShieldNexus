from typing import Literal

from pydantic import Field

from app.schemas.common import Schema

# `confirm_fraud` is the reviewer's label that the evidence supports SIU referral. It is recorded
# as a training label and an audit entry; it does not deny a claim or notify a provider.
DecisionValue = Literal["confirm_fraud", "needs_info", "false_positive", "reassign"]
DECISION_LABEL = {"confirm_fraud": 1, "false_positive": 0, "needs_info": None, "reassign": None}
DECISION_STATUS = {"confirm_fraud": "confirmed", "false_positive": "false_positive", "needs_info": "needs_info", "reassign": "in_review"}


class LineDecisionIn(Schema):
    line_id: str
    decision: Literal["confirm", "dismiss", "review"]


class DecisionIn(Schema):
    decision: DecisionValue
    notes: str = Field(min_length=10, max_length=5000)
    line_decisions: list[LineDecisionIn] = Field(default_factory=list)
    next_action: str | None = Field(default=None, max_length=100)
    assignee: str | None = Field(default=None, max_length=100)  # external user id, for `reassign`


class AssignIn(Schema):
    case_id: str
    assignee: str = Field(min_length=1, max_length=100)  # external user id such as AUD-007


class OptimizeIn(Schema):
    num_investigators: int = Field(default=3, ge=1, le=500)
    hours_per_investigator: float = Field(default=20, gt=0, le=80)
    min_evidence_strength: float = Field(default=0.5, ge=0, le=1)
    max_cases: int | None = Field(default=None, ge=1, le=10_000)


class CounterfactualIn(Schema):
    remove_signals: list[str] | None = None  # signal names to remove; default tries each in turn
