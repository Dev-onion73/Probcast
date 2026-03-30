import time
import os
import yaml
import random
from fastapi import FastAPI, Query
import uvicorn

CONFIG_PATH = os.environ.get("CONNECTORS_CONFIG_PATH", "config/connectors.yaml")
REGIMES_PATH = "config/regimes.yaml"

with open(CONFIG_PATH) as f:
    connectors_conf = yaml.safe_load(f)
with open(REGIMES_PATH) as f:
    TREND_CURVES = yaml.safe_load(f)["regimes"]

# Collect all configured entities
ENTITIES = {e["id"]: e for conn in connectors_conf["connectors"] for e in conn.get("entities", [])}

LOGS = {
    "cpu_overload":    {"level": "CRITICAL", "unit": "kernel", "message": "CPU overload: run queue length exceeds core count"},
    "cpu_overload_precursor": {"level": "WARNING", "unit": "kernel", "message": "CPU soft lockup detected"},
    "memory_exhaustion": {"level": "CRITICAL", "unit": "kernel", "message": "Memory exhaustion: no free pages available"},
    "memory_exhaustion_precursor": {"level": "WARNING", "unit": "kernel", "message": "kswapd0: page allocation stalls"},
    "storage_failure": {"level": "CRITICAL", "unit": "kernel", "message": "Storage failure: device sda unresponsive"},
    "storage_failure_precursor": {"level": "WARNING", "unit": "kernel", "message": "EXT4-fs error (sda1): ext4_find_entry:1455"},
    "network_downtime": {"level": "CRITICAL", "unit": "NetworkManager", "message": "Network downtime: interface eth0 down"},
    "network_downtime_precursor": {"level": "WARNING", "unit": "NetworkManager", "message": "device eth0: link speed below threshold"},
    "service_crash": {"level": "CRITICAL", "unit": "systemd", "message": "Service app.service: Service crashed"},
    "service_crash_precursor": {"level": "WARNING", "unit": "app.service", "message": "Health check response time 200ms exceeds threshold"},
    "dependency_timeout": {"level": "CRITICAL", "unit": "app.service", "message": "Dependency timeout: db.service failed within SLA"},
    "dependency_timeout_precursor": {"level": "WARNING", "unit": "app.service", "message": "Downstream call to db.service exceeded 3000ms"},
    "normal": {"level": "INFO", "unit": "systemd", "message": "All metrics normal"}
}

# Full supported regime list (expand to match your regimes.yaml exactly)
ALL_CLASSES = list(TREND_CURVES.keys())

SWITCH_EVERY = 6  # Ticks before random regime change for variety

entity_state = {}
app = FastAPI()

@app.on_event("startup")
def _init_states():
    now = int(time.time())
    for eid in ENTITIES:
        regime = random.choice(ALL_CLASSES)
        entity_state[eid] = {
            "regime": regime,
            "tick_idx": 0,
            "last_switch": now
        }

def _get_any_metric_for_regime(regime):
    # Return first metric key for this regime
    for k in TREND_CURVES[regime]:
        if isinstance(TREND_CURVES[regime][k], list):
            return k
    raise KeyError(f"No metric curve found in TREND_CURVES[{regime}]")

def _maybe_advance_regime(st, eid):
    # Randomly cycle to a new regime after SWITCH_EVERY ticks
    if st["tick_idx"] >= SWITCH_EVERY:
        new_regime = random.choice(ALL_CLASSES)
        st["regime"] = new_regime
        st["tick_idx"] = 0
        st["last_switch"] = int(time.time())

@app.get("/metrics/data")
def metrics_data(entity_id: str = Query(...), start_ts: float = Query(...), end_ts: float = Query(...)):
    meta = ENTITIES[entity_id]["metadata"]
    res = []
    ts = int(start_ts)
    while ts <= int(end_ts):
        regime = random.choice(ALL_CLASSES)   # <-- random regime for every tick
        metric_key = _get_any_metric_for_regime(regime)
        curve_len = len(TREND_CURVES[regime][metric_key])
        i = random.randint(0, curve_len-1)
        for m in TREND_CURVES[regime]:
            value_list = TREND_CURVES[regime][m]
            if len(value_list) == 0:
                continue
            val = value_list[i % len(value_list)]
            rec = {
                "entity_id": entity_id,
                "source": "mock",
                "metric_type": m,
                "value": val,
                "timestamp": ts,
                "metadata": meta
            }
            res.append(rec)
        ts += 60
    return res

@app.get("/journal/data")
def journal_data(entity_id: str = Query(...), start_ts: float = Query(...), end_ts: float = Query(...)):
    meta = ENTITIES[entity_id]["metadata"]
    res = []
    ts = int(start_ts)
    while ts <= int(end_ts):
        regime = random.choice(ALL_CLASSES) # <-- random regime every tick
        metric_key = _get_any_metric_for_regime(regime)
        curve_len = len(TREND_CURVES[regime][metric_key])
        idx = random.randint(0, curve_len-1)
        logdef = LOGS.get(regime, LOGS["normal"])
        is_anchor = ("precursor" not in regime and idx == curve_len-1)
        log = {
            "entity_id": entity_id,
            "source": "mock",
            "level": logdef["level"] if not is_anchor else "CRITICAL",
            "unit": logdef["unit"],
            "message": logdef["message"],
            "timestamp": ts,
            "metadata": meta,
            "tags": {"is_anchor": is_anchor}
        }
        res.append(log)
        ts += 60
    return res

@app.get("/health")
def health():
    return {"status": "ok", "entities": list(ENTITIES.keys())}

if __name__ == "__main__":
    port = int(os.environ.get("COMBINED_MOCK_PORT", "8101"))
    print(f"[curve_mock_server] Serving fixed regime curves and logs with regime cycling on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)