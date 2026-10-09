#!/bin/sh
set -e

# Only the API container migrates, so the worker and scheduler never race it.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "Applying database migrations"
  alembic upgrade head
  python -c "
import asyncio
from app.db.seed.seed_coverage_rules import seed_coverage_rules
from app.db.session import session_scope, dispose_engine

async def main():
    async with session_scope() as db:
        print('Coverage rules loaded:', await seed_coverage_rules(db))
    await dispose_engine()

asyncio.run(main())
"
fi

exec "$@"
