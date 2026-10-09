from datetime import date

from pydantic import Field, field_validator

from app.schemas.common import Schema


class LineIn(Schema):
    line_id: str = Field(min_length=1, max_length=100)
    cpt_code: str | None = Field(default=None, max_length=20)
    modifiers: list[str] = Field(default_factory=list, max_length=8)
    units: int = Field(default=1, ge=0, le=9999)
    billed_amount: float = Field(default=0, ge=0, le=1e9)
    paid_amount: float = Field(default=0, ge=0, le=1e9)
    service_date: date | None = None
    diagnosis_pointer: list[int] = Field(default_factory=list, max_length=12)

    @field_validator("cpt_code")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v


class ClaimIn(Schema):
    claim_id: str = Field(min_length=1, max_length=100)
    member_id: str = Field(min_length=1, max_length=100)
    provider_id: str = Field(min_length=1, max_length=100)
    facility_id: str | None = Field(default=None, max_length=100)
    referring_provider_id: str | None = Field(default=None, max_length=100)
    service_date: date
    claim_type: str = Field(default="professional", max_length=50)
    total_billed: float = Field(ge=0, le=1e9)
    total_paid: float | None = Field(default=None, ge=0, le=1e9)
    diagnosis_codes: list[str] = Field(default_factory=list, max_length=25)
    lines: list[LineIn] = Field(default_factory=list, max_length=200)
    plan_type: str | None = Field(default=None, max_length=50)
    policy_start_date: date | None = None
    pre_auth_number: str | None = Field(default=None, max_length=100)
    member_age: int | None = Field(default=None, ge=0, le=125)
    service_location: str | None = Field(default=None, max_length=10)
    documents_provided: list[str] | None = None
    # Extra coverage inputs (sum_insured, riders, accident, hospitalisation_hours, ...).
    attributes: dict = Field(default_factory=dict)

    @field_validator("diagnosis_codes")
    @classmethod
    def _dx_upper(cls, v: list[str]) -> list[str]:
        return [c.strip().upper() for c in v if c and c.strip()]


class BatchIn(Schema):
    claims: list[dict] = Field(min_length=1)


class ClaimAccepted(Schema):
    claim_id: str
    status: str
    job_id: str | None
    estimated_completion_seconds: int = 5
    duplicate: bool = False


class CsvIngestIn(Schema):
    csv_text: str = Field(min_length=1, max_length=20_000_000)
    use_field_mapping: bool = True
