from fastapi import APIRouter, Depends

from app.deps import Ctx, require
from app.detection.ml.registry import registry
from app.detection.rules.registry import RuleEngine
from app.services import model_service

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", summary="Model versions")
async def list_models(ctx: Ctx = Depends(require("models:read"))):
    versions = await model_service.list_versions(ctx.db)
    return {
        "versions": [model_service.summary(m) for m in versions],
        "serving": registry.current_version(),
        "rules": RuleEngine(disabled=set((ctx.tenant.config or {}).get("disabled_rules", []))).catalogue(),
    }


@router.get("/{version}", summary="Model card")
async def model_card(version: str, ctx: Ctx = Depends(require("models:read"))):
    return model_service.card(await model_service.get(ctx.db, version))


@router.get("/{version}/card", summary="Model card as JSON: both evaluation splits, limitations, bias analysis")
async def model_card_json(version: str, ctx: Ctx = Depends(require("models:read"))):
    return model_service.card(await model_service.get(ctx.db, version))


@router.post("/{version}/deploy", summary="Deploy a model version (admin)")
async def deploy(version: str, ctx: Ctx = Depends(require("models:deploy"))):
    row = await model_service.deploy(ctx.db, version, ctx.principal, ctx.request)
    await ctx.db.commit()
    return {**model_service.summary(row), "message": f"Version {version} is now used for scoring new claims. Existing scores are unchanged until claims are reprocessed."}
