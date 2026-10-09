from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule


class ProviderValidity(Rule):
    name = "provider_validity"
    description = "The billing provider is not on the tenant's provider file, or is inactive or unlicensed."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        p = ctx.provider
        # Tenants that have not loaded a provider file would otherwise flag every claim.
        if not ctx.provider_master_loaded or not ctx.claim.provider_id:
            return None
        if not p.known:
            return self.signal(0.6, {"reason": "Provider ID is not on the provider file", "provider_id": p.provider_id}, ["provider_id"])
        if p.license_status in ("revoked", "suspended", "expired"):
            return self.signal(0.9, {"reason": f"Provider licence status is '{p.license_status}'", "provider_id": p.provider_id}, ["provider_id"])
        if not p.active:
            return self.signal(0.75, {"reason": "Provider is marked inactive", "provider_id": p.provider_id}, ["provider_id"])
        return None
