"""Read-only anomaly audit using recorded point-in-time features, not rebuilt history."""
import asyncio
import json
from pathlib import Path
import numpy as np
from sklearn.model_selection import train_test_split
from sqlalchemy import select
from app.db.session import get_sessionmaker
from app.db.seed.synthetic import generate, training_matrix_with_groups
from app.detection.ml.feature_engineering import FEATURES, to_row
from app.detection.ml.registry import ModelRegistry
from app.models import Claim, Tenant

async def main():
    models = ModelRegistry()
    assert models.load()
    X, y, _ = training_matrix_with_groups(generate(seed=7))
    Xtrain, Xtest, ytrain, ytest = train_test_split(X, y, test_size=.25, random_state=7, stratify=y)
    normal = Xtrain[ytrain == 0]
    bounds = np.percentile(normal, [1, 50, 99], axis=0)
    spread = np.std(normal, axis=0)
    async with get_sessionmaker()() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "demo_tenant"))).scalar_one()
        claims = (await db.execute(select(Claim).where(Claim.tenant_id == tenant.id).order_by(Claim.created_at.desc()).limit(200))).scalars().all()
        rows = [(c.claim_id, c.attributes.get("_features"), c.risk_score) for c in claims if (c.attributes or {}).get("_features")]
    result = {"version": models.version, "sample_claims": len(claims), "scored_claims": len(rows), "training_normal_rows": len(normal), "training_feature_ranges": {name: {"min": float(normal[:,i].min()), "p01": float(bounds[0,i]), "median": float(bounds[1,i]), "p99": float(bounds[2,i]), "max": float(normal[:,i].max())} for i,name in enumerate(FEATURES)}, "detectors": {}}
    for name, detector in [("lof", models.lof), ("isolation_forest", models.iforest)]:
        details = []
        for claim_id, features, risk in rows:
            row = np.asarray(to_row(features))
            raw = -float(detector.model.score_samples(detector.scaler.transform([row]))[0])
            score = detector.score(row.tolist())
            deviations = np.abs(row - bounds[1]) / np.maximum(spread, 1e-9)
            furthest = [{"feature": FEATURES[i], "value": float(row[i]), "std_from_median": round(float(deviations[i]),2), "outside_training_range": bool(row[i] < normal[:,i].min() or row[i] > normal[:,i].max())} for i in np.argsort(deviations)[-5:][::-1]]
            details.append({"claim_id": claim_id, "raw": raw, "score": score, "risk": risk, "furthest_features": furthest})
        scores = np.array([d["score"] for d in details])
        test_scores = np.array([detector.score(row.tolist()) for row in Xtest[ytest == 0]])
        result["detectors"][name] = {"low": detector.low, "high": detector.high, "clip_count": int((scores == 1).sum()), "clip_share": float((scores == 1).mean()) if len(scores) else None, "heldout_normal_above_threshold": float((test_scores >= .8).mean()), "heldout_normal_percentiles": np.percentile(test_scores,[50,90,99]).tolist(), "claims": details}
    output = Path("docs/anomaly-calibration-before.json")
    output.write_text(json.dumps(result, indent=2))
    print("Audit:", output)
    print("Scored recent claims:",len(rows),"of",len(claims),"available (up to 200 requested)")
    for name, info in result["detectors"].items():
        print(name, json.dumps({k:v for k,v in info.items() if k != "claims"}))
        for d in info["claims"]:
            if d["claim_id"] in {"CLM-94087300","CLM-97258058"}:
                print("EXAMPLE",name,json.dumps(d))
    print("Clipped LOF feature patterns:")
    from collections import Counter
    print(Counter(f["feature"] for d in result["detectors"]["lof"]["claims"] if d["score"] == 1 for f in d["furthest_features"]))

if __name__ == "__main__":
    asyncio.run(main())
