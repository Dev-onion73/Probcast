import time
from fastapi import FastAPI
import uvicorn
import os
from connectors.noise import fbm_sample
from ingestion.schema import SourceType, MetricType, ResourceRecord, EntityMeta

app = FastAPI()

ENTITY_LIST = [
    {
        "entity_id": "payments-prod-01",
        "baseline_cpu": 0.35,
        "baseline_memory": 0.50,
        "metadata": {
            "host": "payments-prod-01",
            "subnet": "subnet-payments",
            "environment": "production",
            "org": "acme-corp"
        }
    },
    {
        "entity_id": "payments-prod-02",
        "baseline_cpu": 0.28,
        "baseline_memory": 0.42,
        "metadata": {
            "host": "payments-prod-02",
            "subnet": "subnet-payments",
            "environment": "production",
            "org": "acme-corp"
        }
    },
    {
        "entity_id": "auth-prod-01",
        "baseline_cpu": 0.40,
        "baseline_memory": 0.60,
        "metadata": {
            "host": "auth-prod-01",
            "subnet": "subnet-auth",
            "environment": "production",
            "org": "acme-corp"
        }
    },
    {
        "entity_id": "auth-prod-02",
        "baseline_cpu": 0.22,
        "baseline_memory": 0.38,
        "metadata": {
            "host": "auth-prod-02",
            "subnet": "subnet-auth",
            "environment": "production",
            "org": "acme-corp"
        }
    }
]

@app.get("/health")
async def health():
    return {"status": "ok", "entity_ids": [e["entity_id"] for e in ENTITY_LIST]}

@app.get("/data")
async def fetch_data(entity_id: str, start_ts: float, end_ts: float):
    print(f"[mock_prometheus] /data called: entity_id={entity_id}, start_ts={start_ts}, end_ts={end_ts}")
    points = []
    entity = next((e for e in ENTITY_LIST if e["entity_id"] == entity_id), None)
    if not entity:
        print("Entity not found. Returning []")
        return []
    # Limit number of returned points (protect against huge queries)
    MAX_POINTS = 120  # e.g., at most 2 hours at 1/min
    ts = start_ts
    points_generated = 0
    while ts <= end_ts and points_generated < MAX_POINTS:
        cpu = fbm_sample(ts, scale=0.03, seed=hash(entity_id) % 10000) + entity["baseline_cpu"]
        cpu = max(0.0, min(1.0, cpu))
        mem = fbm_sample(ts, scale=0.02, seed=(hash(entity_id)+1) % 10000) + entity["baseline_memory"]
        mem = max(0.0, min(1.0, mem))
        meta = EntityMeta(**entity["metadata"])
        points.append(ResourceRecord(
            entity_id=entity_id,
            source=SourceType.PROMETHEUS,
            metric_type=MetricType.CPU_USAGE,
            value=cpu,
            timestamp=ts,
            metadata=meta
        ).__dict__)
        points.append(ResourceRecord(
            entity_id=entity_id,
            source=SourceType.PROMETHEUS,
            metric_type=MetricType.MEMORY_USAGE,
            value=mem,
            timestamp=ts,
            metadata=meta
        ).__dict__)
        ts += 60
        points_generated += 1
    print(f"[mock_prometheus] Returning {len(points)} points for {entity_id}")
    return points

if __name__ == "__main__":
    port = int(os.environ.get("MOCK_PROMETHEUS_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)