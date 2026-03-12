import time
from fastapi import FastAPI
import uvicorn
import os
import random
import math
from typing import List, Dict, Any
from ingestion.schema import SourceType, JournalLevel, JournalRecord, EntityMeta
from connectors.noise import perlin_noise

app = FastAPI()

FAILURE_EVENT_SEQUENCES = {
    "cpu_overload": [
        (-1800, "WARNING",  "kernel",    "CPU soft lockup detected on CPU#N"),
        (-1200, "WARNING",  "kernel",    "RCU stall warning: N seconds"),
        ( -900, "ERROR",    "kernel",    "watchdog: BUG: soft lockup - CPU#N stuck for Ns"),
        ( -600, "ERROR",    "systemd",   "Service nginx.service: main process timeout"),
        ( -300, "WARNING",  "kernel",    "scheduler: process N throttled for CPU bandwidth"),
        ( -120, "ERROR",    "kernel",    "NMI watchdog: hard LOCKUP on cpu N"),
        (  -60, "CRITICAL", "systemd",   "Service nginx.service: State change failed"),
        (    0, "CRITICAL", "kernel",    "CPU overload: run queue length N exceeds core count N"),
    ],
    # other failure classes...
    "memory_exhaustion": [
        (-2400, "WARNING",  "kernel",    "kswapd0: page allocation stalls"),
        (-1800, "WARNING",  "kernel",    "swapper: page allocation failure order:0"),
        (-1200, "WARNING",  "kernel",    "vm_memory_pressure: N pages available"),
        ( -900, "ERROR",    "kernel",    "Out of memory: kill process N score N"),
        ( -600, "ERROR",    "kernel",    "Killed process N total-vm:NkB anon-rss:NkB"),
        ( -300, "CRITICAL", "kernel",    "OOM killer invoked: system OOM"),
        ( -120, "CRITICAL", "systemd",   "Service app.service: Killed by signal SIGKILL"),
        (    0, "CRITICAL", "kernel",    "Memory exhaustion: no free pages available"),
    ],
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
ENTITY_LIST = [
    # As in connector.yaml—fill in configs as appropriate
    {
        "entity_id": "payments-prod-01",
        "metadata": {
            "host": "payments-prod-01",
            "subnet": "subnet-payments",
            "environment": "production",
            "org": "acme-corp"
        },
        "config": {
            "failure_class": "cpu_overload",
            "failure_start_offset": 7200,
            "precursor_window": 3600
        }
    },
    {
        "entity_id": "payments-prod-02",
        "metadata": {
            "host": "payments-prod-02",
            "subnet": "subnet-payments",
            "environment": "production",
            "org": "acme-corp"
        },
        "config": {}
    },
    {
        "entity_id": "auth-prod-01",
        "metadata": {
            "host": "auth-prod-01",
            "subnet": "subnet-auth",
            "environment": "production",
            "org": "acme-corp"
        },
        "config": {
            "failure_class": "memory_exhaustion",
            "failure_start_offset": 9000,
            "precursor_window": 2400
        }
    },
    {
        "entity_id": "auth-prod-02",
        "metadata": {
            "host": "auth-prod-02",
            "subnet": "subnet-auth",
            "environment": "production",
            "org": "acme-corp"
        },
        "config": {}
    }
]

def generate_normal_events(start_ts: float, end_ts: float, entity_id: str) -> List[Dict[str, Any]]:
    t = start_ts
    events = []
    seed = abs(hash(entity_id)) % 9999
    random.seed(seed)
    i = 0
    while t <= end_ts:
        # Use slow perlin noise (changing over hours) to modulate event rate
        noise_scale = 0.5 + 0.5 * perlin_noise(t / 7200, scale=1.0, seed=seed)
        # Noise-modulated event probability
        if random.random() < (0.01 + 0.03 * noise_scale):  # From ~0.01 to ~0.04 chance per 10s
            ev_idx = int((len(NORMAL_EVENT_POOL) - 1) * abs(perlin_noise(t / 600, scale=1.0, seed=(seed + i) % 9907)))
            
            ev_idx = ev_idx % len(NORMAL_EVENT_POOL)  # Always in-bounds!
            level, unit, message = NORMAL_EVENT_POOL[ev_idx]
            level, unit, message = NORMAL_EVENT_POOL[ev_idx]
            events.append({
                "level": level,
                "unit": unit,
                "message": message,
                "timestamp": t + 2 * perlin_noise(t / 900, scale=15.0, seed=seed),  # jitter up to ±30s
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
    return {"status": "ok", "entity_ids": [e["entity_id"] for e in ENTITY_LIST]}

@app.get("/data")
async def fetch_data(entity_id: str, start_ts: float, end_ts: float):
    print(f"[mock_journal] /data: {entity_id} {start_ts}..{end_ts}")
    entity = next((e for e in ENTITY_LIST if e["entity_id"] == entity_id), None)
    if not entity:
        print("Entity not found. Returning []")
        return []
    meta = EntityMeta(**entity["metadata"])
    records = []
    # --- Add smoothened/jittered normal events ---
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

    # --- Add failure sequence, if configured and window includes fail event ---
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

    # Sort all events by timestamp
    out = sorted(records, key=lambda x: x["timestamp"])
    print(f"[mock_journal] Returning {len(out)} records")
    return out

if __name__ == "__main__":
    port = int(os.environ.get("MOCK_JOURNAL_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)