import numpy as np
import random
import json
from datetime import datetime, timedelta

# Core metric names
METRICS = [
    'cpu_usage', 'memory_usage', 'disk_io_read', 'disk_io_write',
    'network_rx', 'network_tx', 'request_rate', 'latency'
]
FAILURE_CLASSES = [
    "cpu_overload", "memory_exhaustion", "storage_failure",
    "network_downtime", "service_crash", "dependency_timeout", "normal"
]

def sample_normal_series(baseline, n_points, drift=0.03, seed=None):
    rng = np.random.default_rng(seed)
    trend = rng.normal(0, drift, size=n_points).cumsum()
    noise = rng.normal(0, 0.03, size=n_points)
    return np.clip(baseline + trend + noise, 0, 1)

def inject_failure_pattern(class_type, precursor_len, n_points, seed=None):
    rng = np.random.default_rng(seed)
    m = {}
    if class_type == "cpu_overload":
        climb = np.linspace(0.45, 0.89, precursor_len) + rng.normal(0,0.01,precursor_len)
        plateau = np.full(n_points - precursor_len, 0.89) + rng.normal(0,0.01,n_points-precursor_len)
        m['cpu_usage'] = np.concatenate([climb, plateau])
    elif class_type == "memory_exhaustion":
        climb = np.linspace(0.5, 0.92, precursor_len) + rng.normal(0,0.01,precursor_len)
        plateau = np.full(n_points - precursor_len, 0.92) + rng.normal(0,0.01,n_points-precursor_len)
        swap = np.zeros(n_points)
        swap[-10:] = np.linspace(0.1, 0.98, 10) + rng.normal(0,0.01,10)
        m['memory_usage'] = np.concatenate([climb, plateau])
        m['swap_usage'] = swap
    elif class_type == "storage_failure":
        read = np.concatenate([np.random.uniform(0.1,0.2,n_points-precursor_len), np.random.uniform(0.85,0.95,precursor_len)])
        write = np.concatenate([np.random.uniform(0.12,0.16,n_points-precursor_len), np.random.uniform(0.01,0.03,precursor_len)])
        m['disk_io_read'] = read
        m['disk_io_write'] = write
    elif class_type == "network_downtime":
        collapse = np.linspace(0.15, 0.01, precursor_len) + rng.normal(0,0.01,precursor_len)
        pre = np.full(n_points - precursor_len, 0.18) + rng.normal(0,0.01,n_points-precursor_len)
        m['network_rx'] = np.concatenate([pre, collapse])
        m['network_tx'] = np.concatenate([pre, collapse])
    elif class_type == "service_crash":
        req = np.concatenate([np.random.uniform(0.18,0.30,n_points-precursor_len), np.full(precursor_len, 0.01)])
        m['request_rate'] = req
    elif class_type == "dependency_timeout":
        lat = np.concatenate([np.random.uniform(0.18,0.26,n_points-precursor_len), np.random.uniform(0.55,0.95,precursor_len)])
        m['latency'] = lat
    return m

def generate_journal_sequence(class_type, window_len, event_times, anchor_time):
    # This is a stub; injects plausible events at the given anchor
    journal_events = []
    if class_type == "cpu_overload":
        journal_events = [
            {"offset_seconds": -1800, "level": "WARNING", "message": "CPU soft lockup detected on CPU#3"},
            {"offset_seconds": -900, "level": "ERROR", "message": "watchdog: soft lockup - CPU#3 stuck"},
            {"offset_seconds": 0, "level": "CRITICAL", "message": "CPU overload: run queue length exceeds core count"}
        ]
    # Add more for each class as in your guide...
    # Adjust time offsets/gap as needed.
    # For normal regime: low-severity, random event types.
    return journal_events

def create_labeled_event(entity_id, class_type, start_time, window_len=60):
    n_points = window_len
    precursor_len = int(window_len * 0.3)  # 30% precursor, rest for baseline/anchor
    baseline = np.random.uniform(0.2,0.4)

    # Prepare resource data
    resource_series = {metric: sample_normal_series(baseline, n_points) for metric in METRICS}
    if class_type != "normal":
        injected = inject_failure_pattern(class_type, precursor_len, n_points)
        resource_series.update(injected)

    anchor_time = start_time + window_len*60
    event_times = [start_time + i*60 for i in range(n_points)]
    journal_sequence = generate_journal_sequence(class_type, window_len, event_times, anchor_time)

    return {
        "entity_id": entity_id,
        "failure_class": class_type,
        "failure_timestamp": anchor_time if class_type != "normal" else None,
        "window_start": start_time,
        "window_end": anchor_time,
        "resource_series": {k: [float(x) for x in v] for k,v in resource_series.items()},
        "journal_series": journal_sequence,
        "label": class_type,
        "confidence": 1.0 if class_type != "normal" else 0.97,
    }

def main():
    n_samples = 500
    entity_id = "payments-prod-01"
    START = int(datetime(2024,1,1,0,0).timestamp())
    all_classes = FAILURE_CLASSES

    all_events = []
    for sample_id in range(n_samples):
        # Balance normal and failures
        if sample_id % 8 == 0:
            class_type = random.choice([c for c in FAILURE_CLASSES if c != "normal"])
        else:
            class_type = "normal"
        sample_start = START + sample_id*3600  # e.g. one per hour
        ev = create_labeled_event(entity_id, class_type, sample_start, window_len=60)
        all_events.append(ev)

    # Write to JSONL for downstream pipeline
    with open("synthetic_labeled_events.jsonl","w") as f:
        for event in all_events:
            f.write(json.dumps(event))
            f.write("\n")

if __name__ == "__main__":
    main()