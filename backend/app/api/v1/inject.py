from fastapi import APIRouter, Depends

from app.core.exceptions import Forbidden
from app.deps import Ctx, require
from app.schemas.feedback import InjectIn
from app.services import inject_service

router = APIRouter(prefix="/inject", tags=["demo"])


@router.get("/schemes", summary="Available test schemes")
async def schemes(ctx: Ctx = Depends(require("inject:run"))):
    return {"schemes": [{"scheme": k, "description": v} for k, v in inject_service.SCHEMES.items()], "enabled": ctx.tenant.is_demo}


@router.post("", summary="Inject a synthetic test scheme (demo tenants only)")
async def inject(body: InjectIn, ctx: Ctx = Depends(require("inject:run"))):
    # The tenant always comes from the caller's credentials. A tenant_id in the body is accepted
    # for compatibility but can never redirect the injection into another tenant.
    if body.tenant_id and body.tenant_id not in (ctx.tenant.slug, str(ctx.tenant.id)):
        raise Forbidden("You can only inject test schemes into your own tenant.")
    out = await inject_service.inject(ctx.db, ctx.tenant, body.scheme, ctx.principal, ctx.request)
    await ctx.db.commit()
    return out
