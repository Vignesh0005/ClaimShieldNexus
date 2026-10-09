from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.exceptions import ValidationFailed
from app.deps import Ctx, context, require
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", summary="Audit log for the tenant")
async def global_audit(
    ctx: Ctx = Depends(require("audit:read")),
    action: str | None = Query(None, description="Action or prefix, such as 'case.'"),
    actor: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    rows, total = await audit_service.query(ctx.db, ctx.tenant.id, action=action, actor=actor, since=since, until=until, limit=limit, offset=offset)
    return {"events": [audit_service.to_dict(e) for e in rows], "total": total, "limit": limit, "offset": offset}


# Things that happen in the browser (a CSV export, a PDF download) leave no server request of
# their own, so the client reports them. Only these names are accepted, and the entry is recorded
# under the authenticated caller and marked as client-reported.
CLIENT_EVENTS = {"export.queue_csv", "export.audit_csv", "export.brief_pdf", "print.briefs", "overlay.sent_to_siu"}


@router.post("/events", summary="Record a client-side action (exports, prints) in the audit trail")
async def client_event(body: dict, ctx: Ctx = Depends(context)):
    action = str(body.get("action", ""))
    if action not in CLIENT_EVENTS:
        raise ValidationFailed(f"Unknown client event '{action}'.", allowed=sorted(CLIENT_EVENTS))
    case_id = body.get("case_id")
    await ctx.audit.log(f"client.{action}", "case" if case_id else "client", str(case_id)[:100] if case_id else None, principal=ctx.principal, details={"note": str(body.get("detail", ""))[:300], "client_reported": True}, request=ctx.request)
    await ctx.db.commit()
    return {"recorded": True}


@router.get("/retention", summary="Data retention policy")
async def retention(ctx: Ctx = Depends(require("audit:read"))):
    return audit_service.retention_policy()


@router.get("/user/{user_id}", summary="Actions by one user")
async def user_actions(user_id: str, ctx: Ctx = Depends(require("audit:read")), limit: int = Query(200, ge=1, le=1000)):
    rows, total = await audit_service.query(ctx.db, ctx.tenant.id, actor=user_id, limit=limit)
    return {"user_id": user_id, "events": [audit_service.to_dict(e) for e in rows], "total": total}


@router.post("/export", summary="Export the audit log as CSV")
async def export(ctx: Ctx = Depends(require("audit:read")), since: datetime | None = None, until: datetime | None = None):
    rows, total = await audit_service.query(ctx.db, ctx.tenant.id, since=since, until=until, limit=50_000)
    await ctx.audit.log("audit.exported", "audit", None, principal=ctx.principal, details={"rows": len(rows), "total": total}, request=ctx.request)
    await ctx.db.commit()
    return Response(audit_service.to_csv(rows), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'})


@router.get("/{case_id}", summary="Audit trail for a case")
async def case_audit(case_id: str, ctx: Ctx = Depends(require("audit:read")), limit: int = Query(200, ge=1, le=1000)):
    rows, total = await audit_service.query(ctx.db, ctx.tenant.id, resource_type="case", resource_id=case_id, limit=limit)
    return {"case_id": case_id, "events": [audit_service.to_dict(e) for e in rows], "total": total}
