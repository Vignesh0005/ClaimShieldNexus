"""Builds a working demo: schema, coverage rules, a trained model, a demo tenant with users, and
synthetic claims processed through the real pipeline.

    python -m scripts.seed_demo [--claims-days 120] [--second-tenant]

Safe to re-run: existing tenants, users and claims are left as they are."""
import argparse
import asyncio
import time
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.core.logging import configure_logging
from app.core.security import create_access_token
from app.db.seed.seed_coverage_rules import seed_coverage_rules
from app.db.seed.seed_demo_tenant import seed_tenant
from app.db.seed.seed_synthetic import seed_claims, seed_reference_data
from app.db.seed.synthetic import generate, training_matrix_with_groups
from app.db.session import create_all, dispose_engine, session_scope
from app.detection.ml.registry import registry
from app.detection.ml.training import set_current, train_models
from app.services import model_service


async def ensure_model() -> None:
    if registry.load():
        print(f"Model {registry.version} already deployed.")
        return
    print("No deployed model found; training v1.0.0 on synthetic claims.")
    out = Path(get_settings().artifacts_dir)
    X, y, groups = training_matrix_with_groups(generate())
    meta = train_models(X, y, "v1.0.0", out, groups=groups)
    from scripts.train_xgboost import render_model_card

    Path("docs").mkdir(exist_ok=True)
    Path("docs/model_card.md").write_text(render_model_card(meta), encoding="utf-8")
    set_current(out, "v1.0.0")
    async with session_scope() as db:
        await model_service.register(db, meta, str(out / "v1.0.0"), deployed=True, notes="Trained on synthetic claims with planted patterns.")
    registry.load()
    split = meta["evaluation"]["provider_split"] or {}
    print(f"  random split F1={meta['metrics']['f1']}  provider split F1={split.get('f1', 'not measured')}  (synthetic data; see docs/model_card.md)")


async def seed_one(name: str, slug: str, *, seed: int, days: int, providers: int, members: int, rate: float) -> None:
    async with session_scope() as db:
        tenant, api_key = await seed_tenant(db, name, slug)
    data = generate(seed=seed, n_providers=providers, n_members=members, days=days, end=date.today(), daily_rate=rate)
    started = time.perf_counter()
    async with session_scope(tenant.id) as db:
        await seed_reference_data(db, tenant, data)
        stats = await seed_claims(db, tenant, data, progress=lambda done, total: print(f"  {slug}: {done}/{total} claims", end="\r"))
    print(f"  {slug}: {stats['ingested']} claims processed, {stats['skipped']} already present, {stats['rejected']} rejected in {time.perf_counter() - started:.0f}s")
    if api_key:
        print(f"  {slug} API key (shown once): {api_key}")
    token = create_access_token(subject="ADM-002", tenant_id=tenant.id, role="admin", platform_admin=True)
    print(f"  {slug} admin token (8 hours): {token}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claims-days", type=int, default=120)
    parser.add_argument("--second-tenant", action="store_true", help="Also seed a small second tenant to show isolation")
    args = parser.parse_args()
    get_settings().log_level = "WARNING"  # per-claim info logs would drown the progress output
    configure_logging()
    await create_all()
    async with session_scope() as db:
        print(f"Coverage rules loaded: {await seed_coverage_rules(db)}")
    await ensure_model()
    await seed_one("Meridian Health Plan", "meridian", seed=7, days=args.claims_days, providers=60, members=500, rate=0.2)
    if args.second_tenant:
        await seed_one("Northlake Mutual", "northlake", seed=11, days=60, providers=25, members=200, rate=0.12)
    await dispose_engine()
    print("\nDone. Start the API with:  uvicorn app.main:app --reload")
    print("Then open http://localhost:8000/docs and authorise with the admin token above.")


if __name__ == "__main__":
    asyncio.run(main())
