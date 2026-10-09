from typing import Literal

from pydantic import Field

from app.schemas.common import Schema


class FeedbackIn(Schema):
    case_id: str
    decision: Literal["confirmed_fraud", "false_positive", "needs_info"]
    final_label: Literal[0, 1] | None = None
    reviewer_id: str | None = None
    notes: str | None = Field(default=None, max_length=5000)
    time_spent_seconds: int | None = Field(default=None, ge=0, le=7 * 24 * 3600)


class InjectIn(Schema):
    scheme: str
    tenant_id: str | None = None


class CopilotInvestigateIn(Schema):
    case_id: str
    include_counterfactuals: bool = True
    include_plain_language: bool = True


class CopilotAskIn(Schema):
    case_id: str
    question: str = Field(min_length=3, max_length=1000)
