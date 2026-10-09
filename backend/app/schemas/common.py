from pydantic import BaseModel, ConfigDict

DISCLAIMER = "Synthetic demo. Not a fraud determination."


class Schema(BaseModel):
    # protected_namespaces is cleared because the API contract uses fields such as model_version.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=(), extra="ignore")


class Page(Schema):
    items: list
    total: int
    limit: int
    offset: int
