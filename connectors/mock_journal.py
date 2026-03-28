import time
from fastapi import FastAPI
import uvicorn
import os
import random
from typing import List, Dict, Any
from ingestion.schema import SourceType, JournalLevel, JournalRecord, EntityMeta
from connectors.noise import perlin_noise

import yaml

def load_entity_list():
    config_path = os.environ.get("CONNECTORS_CONFIG_PATH") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "config", "connectors.yaml"
    )
    config_path = os.path.normpath(config_path)
    with open(config_path) as f:
        connectors = yaml.safe_load(f)["connectors"]
    my_id = "mock_journal"
    my_block = next(c for c in connectors if c["id"] == my_id)
    return my_block["entities"]

ENTITY_LIST = load_entity_list()

FAILURE_EVENT_SEQUENCES = {
    # [As in your current file, unchanged... all classes defined]
    # ...
}

NORMAL_EVENT_POOL = [
    ("INFO", "sshd.service", "Accepted publickey for user from 172.16.1.1"),
    ("INFO", "systemd", "Started Session N of user root."),
    ("INFO", "kernel", "EXT4-fs (sda1): re-mounted. Opts: data=ordered"),
    ("INFO", "cron", "Started Regular background program processing daemon."),
    ("WARNING", "kernel", "ACPI BIOS Error (bug)"),
    ("WARNING", "systemd", "Session N has expired"),
    ("ERROR", "cron", "Failed to execute scheduled job"),
]

app = FastAPI()

def generate_normal_events(start_ts: float, end_ts: float, entity_id: str) -> List[Dict[str, Any]]:
    t = start_ts
    events = []
    seed = abs(hash(entity_id)) % 9999
    random.seed(seed)
    i = 0
    while t <= end_ts:
        noise_scale = 0.5 + 0.5 * perlin_noise(t / 7200, scale=1.0, seed=seed)
        if random.random() < (0.01 + 0.03 * noise_scale):
            ev_idx = int((len(NORMAL_EVENT_POOL) - 1) * abs(perlin_noise(t / 600, scale=1.0, seed=(seed + i) % 9907)))
            ev_idx = ev_idx % len(NORMAL_EVENT_POOL)
            level, unit, message = NORMAL_EVENT_POOL[ev_idx]
            events.append({
                "level": level,
                "unit": unit,
                "message": message,
                "timestamp": t + 2 * perlin_noise(t / 900, scale=15.0, seed=seed),
            })
        t += 10
        i += 1
    return events

def generate_failure_events(failure_class: str, anchor_time: float) -> List[Dict[str, Any]]:
    seq = FAILURE_EVENT_SEQUENCES.get(failure_class, [])
    events = []
    for offset, level, unit, message in seq:
        events.append({
            "level": level,
            "unit": unit,
            "message": message,
            "timestamp": anchor_time + offset,
            "tags": {"is_anchor": offset == 0}
        })
    return events

@app.get("/health")
async def health():
    return {"status": "ok", "entity_ids": [e["id"] for e in ENTITY_LIST]}

@app.get("/data")
async def fetch_data(entity_id: str, start_ts: float, end_ts: float):
    print(f"[mock_journal] /data: {entity_id} {start_ts}..{end_ts}")
    entity = next((e for e in ENTITY_LIST if e["id"] == entity_id), None)
    if not entity:
        print("Entity not found. Returning []")
        return []
    meta = EntityMeta(**entity["metadata"])
    records = []
    normal_events = generate_normal_events(start_ts, end_ts, entity_id)
    for ev in normal_events:
        records.append(JournalRecord(
            entity_id=entity_id,
            source=SourceType.JOURNAL,
            level=JournalLevel(ev["level"]),
            unit=ev["unit"],
            message=ev["message"],
            timestamp=ev["timestamp"],
            metadata=meta,
            tags={}
        ).__dict__)

    config = entity.get("config", {})
    failure_class = config.get("failure_class")
    failure_offset = config.get("failure_start_offset", None)
    current_time = time.time()
    demo_start = current_time - 10800  # Simulate demo started 3h ago
    if failure_class and failure_offset is not None:
        anchor_time = demo_start + failure_offset
        failure_events = generate_failure_events(failure_class, anchor_time)
        for fev in failure_events:
            ts = fev["timestamp"]
            if start_ts <= ts <= end_ts:
                records.append(JournalRecord(
                    entity_id=entity_id,
                    source=SourceType.JOURNAL,
                    level=JournalLevel(fev["level"]),
                    unit=fev["unit"],
                    message=fev["message"],
                    timestamp=ts,
                    metadata=meta,
                    tags=fev.get("tags", {})
                ).__dict__)

    out = sorted(records, key=lambda x: x["timestamp"])
    print(f"[mock_journal] Returning {len(out)} records")
    return out

if __name__ == "__main__":
    port = int(os.environ.get("MOCK_JOURNAL_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)