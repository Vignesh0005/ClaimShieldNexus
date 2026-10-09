from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.config import get_settings
from app.core import perf
from app.core.cache import cache
from app.deps import Ctx, context
from app.models import Claim

router = APIRouter(tags=["health"])


@router.get("/health/performance", summary="Measured detection latency and throughput for this API process")
async def performance(ctx: Ctx = Depends(context)):
    """Figures are measured from claims this process has handled since it started. Nothing here is
    a target or an estimate: with no claims processed, latency is null."""
    settings = get_settings()
    backlog = (await ctx.db.execute(select(func.count()).select_from(Claim).where(Claim.tenant_id == ctx.tenant.id, Claim.processing_status == "processing"))).scalar_one()
    database = settings.database_url.split("+")[0].split(":")[0]
    mode = f"{'in-process' if settings.process_inline else 'Celery workers'}, {database}, {cache.backend} cache"
    return {
        **perf.summary(),
        "backlog": backlog,
        "mode": mode,
        "note": "Measured in this API process only, since it last started. On SQLite with in-process detection, claims are handled one at a time; see docs/scaling.md for the measured benchmark and the path to higher throughput."
        if settings.process_inline
        else "Measured in this API process only. Detection runs on Celery workers, whose latency is reported by each worker.",
    }
