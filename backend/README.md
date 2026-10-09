# ClaimShield Nexus backend

Multi-tenant fraud, waste and abuse (FWA) detection for healthcare payers.

AI detects and explains, a person verifies, and verified outcomes improve the AI. The system never
denies, pends or adjusts a claim. The strongest thing it does by itself is open a case for a reviewer.

> Synthetic demo. Not a fraud determination. All bundled data, coverage rules and code sets are
> illustrative and must be replaced or verified before any real use (see [Before production](#before-production)).

## Run it locally

Needs Python 3.11 or later. Nothing else: with no configuration it uses SQLite, an in-process cache
and in-process background detection.

```bash
python -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.seed_demo --second-tenant   # trains a model, creates demo tenants, processes ~2,200 synthetic claims (takes several minutes)
uvicorn app.main:app --reload                 # http://localhost:8000/docs
pytest                                        # 74 tests, about 25 seconds
```

`seed_demo` prints an API key (for claim ingestion) and an admin token for each tenant. To get a
token for another role in development:

```bash
curl -X POST localhost:8000/api/v1/auth/dev-token -H "content-type: application/json" \
  -d '{"tenant": "meridian", "user": "AUD-007", "role": "siu_investigator"}'
```

That endpoint issues tokens to anyone and does not exist when `ENV=production`.

## Run the full stack

```bash
# in docker/.env:  POSTGRES_PASSWORD=...  JWT_SECRET=...
docker compose -f docker/docker-compose.yml up --build
```

Starts the API, a Celery worker, the Celery scheduler, PostgreSQL (with pgvector) and Redis. The API
container applies migrations and loads the coverage rules. Add `--profile sqs` for the SQS consumer.

## What happens to a claim

```
POST /api/v1/claims (API key)  or  SQS  or  CSV / FHIR / webhook
   -> field mapping -> normalise -> validate -> idempotency check -> stored, 202 returned
   -> detection pipeline (Celery worker, or in-process when there is no Redis)
        1. coverage rules     a failure means "claims staff must look", never fraud, never denial;
                              a blocking coverage result stops here and no FWA score is produced
        2. FWA rules          11 rules, each a pure function with cited evidence
        3. ML                 XGBoost + isolation forest + LOF, with TreeSHAP feature attributions
        4. graph              referral loops, shared addresses
        5. temporal           billing spikes against the provider's own baseline
        6. risk fusion        composite risk, suspicion vs. evidence, member harm
   -> if routed: added to the provider's open case -> SIU queue -> reviewer decision
   -> decision becomes a training label -> candidate model -> deployed only by an admin
```

A claim is routed to the queue when its risk score reaches the tenant's routing threshold
(default 0.70), or when one rule finding is near-certain (confidence 0.90 or more) with evidence
strength of at least 0.50. The second path exists because the composite score needs several
detectors to agree, so a clear-cut exact duplicate would otherwise never reach a reviewer. Turn it
off per tenant with `"route_on_strong_rule": false` in the tenant config.

## Graceful degradation

| If this is unavailable | The system does this | Visible as |
|---|---|---|
| ML model server (`ML_SERVER_URL`) | Scores with local artifacts; circuit breaker stops retrying for 60 s | `ml_degraded: true` on results, `/health/ml-server` |
| Local model artifacts too | Rules, graph and temporal detectors only | `model_version: fallback_rules_only`, a limitation on the case |
| Copilot LLM (`OLLAMA_API_KEY`) | Deterministic explanation from the same evidence | `model: template_fallback` with the reason |
| Redis | In-process cache; detection runs in the API process | `/health/redis` |
| ILP solver | Greedy value-per-hour selection | `optimization_method` in the response |

## Security model

- **Authentication.** `X-API-Key` for machine ingestion (stored only as a SHA-256 hash, shown once,
  rotatable). `Authorization: Bearer` for users: HS256 with `JWT_SECRET`, or Clerk-issued tokens
  when `CLERK_JWKS_URL` is set (tenant and role are read from the token's public metadata).
- **Tenant isolation.** The tenant always comes from the credential. Every service query filters by
  tenant explicitly, and every tenant-bound database session also adds the tenant predicate to all
  ORM reads (`app/db/session.py`), so a query that forgets its filter still returns one tenant's rows.
  An `X-Tenant-Id` header naming another tenant is refused unless the caller is a platform administrator.
- **Roles.** `admin`, `siu_investigator`, `analyst`, `viewer`, plus `api` for keys (ingest only).
  The role stored in the database wins over the token after first sign-in, so role changes and
  deactivation take effect immediately. Permissions are in `app/core/security.py`.
- **Audit.** Every state-changing request and every case view, export and decision is written to
  `audit_logs`. The ORM refuses updates and deletes; on PostgreSQL a trigger enforces the same.
- **Copilot.** Only derived evidence (scores, findings, limitations) is sent to the LLM, never raw
  claims or member identifiers. Output that is malformed or uses accusatory wording is discarded.

`tests/integration/test_tenant_isolation.py` exercises the isolation and role rules.

## Layout

```
app/
  api/v1/            routes (80 paths)             api/middleware/   auth, tenant scope, rate limit, audit, errors
  core/              security, audit, cache, events, metrics, logging
  ingestion/         adapters (CSV, REST, FHIR, webhook, SQS), mapping, normalise, validate, idempotency
  detection/
    coverage/        rules engine + 22 rules in data/coverage_rules.json
    rules/           FWA rules           ml/        models, training, remote client, similarity
    graph/           loops, communities, time travel      temporal/  spikes, z-scores, forecast
    scoring/         fusion, two-axis, member harm, capacity optimizer
    pipeline.py      orchestrator
  explainability/    briefs (Jinja templates), counterfactuals, limitations, copilot
  services/          business logic          workers/   Celery tasks and schedules
  models/            SQLAlchemy              schemas/   Pydantic
  db/                session, migrations (Alembic), seed
scripts/             train, seed, model server, synthetic data, exports
tests/               unit + integration
```

## Two-machine ML setup

On the training machine: `python -m scripts.train_xgboost`, then
`uvicorn scripts.ml_server:app --host 0.0.0.0 --port 8001`. On the application server set
`ML_SERVER_URL=http://<training-machine>:8001`. Only feature vectors cross the network. Set
`ML_SERVER_TOKEN` on the model server and keep it on a trusted network.

## Differences from the original specification

- **Storage types.** Array columns (`diagnosis_codes`, `modifiers`) are JSON/JSONB and `ip_address`
  is text, so the same models run on SQLite and PostgreSQL.
- **Extra tables.** `case_decisions`, `providers`, `members`, `facilities`, `referrals`; a `users`
  table with `external_id`; extra columns such as `claims.processing_status`.
- **Coverage statuses.** A rule can ask for review without blocking FWA detection
  (`on_uncertain: FLAG_FOR_REVIEW`). This is what lets the documented example (a 72-year-old with a
  possible pre-existing condition) be `COVERABLE_WITH_CONDITIONS` and still receive FWA signals.
- **Feature attributions.** XGBoost's native TreeSHAP is used; the `shap` package is optional.
- **Embeddings and FAISS** are optional extras (`requirements-ml-extras.txt`) with built-in
  fallbacks, because they pull in PyTorch. Similar-case search is available through
  `scripts.build_faiss_index` and the model server, and is not yet part of the claim pipeline.
- **Briefs** are rendered from templates over stored evidence rather than written by the LLM, so
  every line is traceable. The LLM is used only by the copilot endpoints.
- **Dev token endpoint** and an **`/api/v1/admin/analytics`**, **forecasts** and **`/claims/ingest/*`**
  group were added.
- `pulp` is pinned below 3 because 3.x ships no solver and changed its API.

## Before production

1. **Coverage rules** are an illustrative encoding of IRDAI health insurance rules. Have a
   compliance owner verify each one against the regulation and the insurer's policy wording.
2. **Code sets** (`app/utils/codes.py`): the NCCI pairs, panels and typical-minutes tables are
   small samples. Load the licensed CPT set and the current CMS NCCI edit files.
3. **The model is trained on synthetic data** with planted patterns, so its reported metrics
   (F1 about 0.95) say nothing about real claims. It also leans on provider volume features.
   Retrain on reviewed production cases and run a bias audit before relying on it.
4. **Not exercised here:** PostgreSQL, Redis, Celery workers, Docker images, SQS/SNS, Clerk token
   verification, Sentry and the live Ollama API. The code paths exist; they were not run because
   none of those services were available on the development machine. Everything else in this
   README was run against SQLite.
5. **Throughput.** In-process detection on SQLite takes roughly 50 to 250 ms per claim. Measure on
   PostgreSQL with several workers before committing to a claims-per-minute figure.
6. **Case numbering** is computed from the highest existing number; under concurrent workers two
   cases can collide on the unique constraint and one task will retry. Use a database sequence.
7. Set `JWT_SECRET` (startup refuses the default in production), restrict `CORS_ORIGINS`, and put
   the API behind TLS.
