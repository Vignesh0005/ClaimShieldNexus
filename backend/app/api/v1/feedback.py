from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.config import get_settings
from app.deps import Ctx, require
from app.schemas.feedback import FeedbackIn
from app.services import feedback_service, model_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _queue_retrain(background: BackgroundTasks, tenant_id, actor: str) -> None:
    if get_settings().process_inline:
        from app.workers.tasks.retrain_task import retrain_inline

        background.add_task(retrain_inline, tenant_id, actor)
    else:
        from app.workers.tasks.retrain_task import train_candidate_model

        train_candidate_model.delay(str(tenant_id), actor)


@router.post("", summary="Submit investigator feedback")
async def submit(body: FeedbackIn, background: BackgroundTasks, ctx: Ctx = Depends(require("feedback:write"))):
    out = await feedback_service.submit(ctx.db, ctx.tenant, body, ctx.principal, ctx.request)
    await ctx.db.commit()
    if out["retrain_triggered"]:
        _queue_retrain(background, ctx.tenant.id, "threshold")
    return out


@router.get("", summary="Recent feedback")
async def list_feedback(ctx: Ctx = Depends(require("models:read")), limit: int = Query(100, ge=1, le=500)):
    return {"items": await feedback_service.list_feedback(ctx.db, ctx.tenant.id, limit)}


@router.get("/queue", summary="Training queue status")
async def queue(ctx: Ctx = Depends(require("models:read"))):
    return await feedback_service.queue_status(ctx.db, ctx.tenant)


@router.post("/retrain", status_code=202, summary="Train a candidate model now (admin)")
async def retrain(background: BackgroundTasks, wait: bool = False, ctx: Ctx = Depends(require("models:deploy"))):
    await ctx.audit.log("model.retrain_requested", "model", None, principal=ctx.principal, request=ctx.request)
    await ctx.db.commit()
    if wait:
        out = await model_service.retrain(ctx.db, ctx.tenant.id, ctx.principal.subject)
        await ctx.db.commit()
        return out
    _queue_retrain(background, ctx.tenant.id, ctx.principal.subject)
    return {"status": "queued", "message": "A candidate model is being trained. It will appear under /models and is not deployed automatically."}
