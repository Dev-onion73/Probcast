import time
import os
import yaml
from fastapi import FastAPI
import uvicorn

from connectors.noise import fbm_sample
from ingestion.schema import SourceType, MetricType, ResourceRecord, EntityMeta

app = FastAPI()

def load_entity_list():
    config_path = os.environ.get("CONNECTORS_CONFIG_PATH") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "config", "connectors.yaml"
    )
    config_path = os.path.normpath(config_path)
    with open(config_path) as f:
        connectors = yaml.safe_load(f)["connectors"]
    my_id = "mock_prometheus"
    my_block = next(c for c in connectors if c["id"] == my_id)
    return my_block["entities"]

ENTITY_LIST = load_entity_list()

@app.get("/health")
async def health():
    return {"status": "ok", "entity_ids": [e["id"] for e in ENTITY_LIST]}

@app.get("/data")
async def fetch_data(entity_id: str, start_ts: float, end_ts: float):
    print(f"[mock_prometheus] /data called: entity_id={entity_id}, start_ts={start_ts}, end_ts={end_ts}")
    points = []
    entity = next((e for e in ENTITY_LIST if e["id"] == entity_id), None)
    if not entity:
        print("Entity not found. Returning []")
        return []
    config = entity.get("config", {})  # robust: some entities may lack config
    baseline_cpu = config.get("baseline_cpu", 0.3)
    baseline_mem = config.get("baseline_memory", 0.4)
    meta = EntityMeta(**entity["metadata"])
    # Limit number of returned points (protect against huge queries)
    MAX_POINTS = 120  # e.g., at most 2 hours at 1/min
    ts = start_ts
    points_generated = 0
    while ts <= end_ts and points_generated < MAX_POINTS:
        cpu = fbm_sample(ts, scale=0.03, seed=hash(entity_id) % 10000) + baseline_cpu
        cpu = max(0.0, min(1.0, cpu))
        mem = fbm_sample(ts, scale=0.02, seed=(hash(entity_id)+1) % 10000) + baseline_mem
        mem = max(0.0, min(1.0, mem))
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