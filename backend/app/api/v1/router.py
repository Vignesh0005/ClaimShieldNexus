from fastapi import APIRouter

from app.api.v1 import integrations, admin, audit, performance, similar, briefs, cases, claims, copilot, counterfactual, coverage, detection, evidence, feedback, funnel, inject, models, network, queue, tenants, users

api_router = APIRouter(prefix="/api/v1")

for module in (claims, coverage, detection, queue, funnel, cases, evidence, counterfactual, network, briefs, copilot, inject, feedback, models, audit, tenants, users, admin, similar, performance):
    api_router.include_router(module.router)

# Additive machine integration routes and outbound webhook registration.
api_router.include_router(integrations.router)
