from prometheus_client import Counter, Gauge, Histogram

claims_ingested = Counter("claimshield_claims_ingested_total", "Total claims ingested", ["tenant_id"])
claims_processed = Counter("claimshield_claims_processed_total", "Claims through the detection pipeline", ["tenant_id", "outcome"])
detection_latency = Histogram("claimshield_detection_latency_seconds", "Detection pipeline latency", buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
ml_degraded = Counter("claimshield_ml_degraded_total", "Claims scored without the ML models")
queue_size = Gauge("claimshield_queue_size", "Open cases in the SIU queue", ["tenant_id"])
model_f1 = Gauge("claimshield_model_f1", "F1 of the deployed model", ["version"])
http_requests = Counter("claimshield_http_requests_total", "HTTP requests", ["method", "status"])
