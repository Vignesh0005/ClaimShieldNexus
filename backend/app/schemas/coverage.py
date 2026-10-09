from datetime import date

from pydantic import Field

from app.schemas.common import Schema


class CoverageEvaluateIn(Schema):
    claim_id: str = Field(min_length=1, max_length=100)
    plan_type: str | None = None
    member_age: int | None = Field(default=None, ge=0, le=125)
    policy_start_date: date | None = None
    service_date: date | None = None
    procedure_code: str | None = None
    procedure_codes: list[str] = Field(default_factory=list)
    diagnosis_codes: list[str] = Field(default_factory=list)
    service_location: str | None = None
    pre_auth_number: str | None = None
    documents_provided: list[str] | None = None
    claim_type: str | None = "professional"
    total_billed: float | None = None
    attributes: dict = Field(default_factory=dict)
