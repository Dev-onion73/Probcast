import os
import numpy as np
import json

FAILURE_CLASSES = [
    "normal",
    "cpu_overload", "memory_exhaustion", "storage_failure",
    "network_downtime", "service_crash", "dependency_timeout"
]

def generate_synthetic_sample(entity_id, failure_class, window_len=60, seed=None):
    np.random.seed(seed)
    metrics = {
        "cpu_usage": np.random.normal(loc=0.35, scale=0.1, size=window_len).tolist(),
        "memory_usage": np.random.normal(loc=0.45, scale=0.08, size=window_len).tolist(),
        "disk_io_read": np.random.normal(loc=0.09, scale=0.04, size=window_len).tolist(),
        "disk_io_write": np.random.normal(loc=0.08, scale=0.03, size=window_len).tolist(),
        "network_rx": np.random.normal(loc=0.12, scale=0.03, size=window_len).tolist(),
        "network_tx": np.random.normal(loc=0.10, scale=0.03, size=window_len).tolist()
    }
    if failure_class != "normal":
        for i in range(-10, 0):
            metrics["cpu_usage"][i] = np.clip(metrics["cpu_usage"][i] + 0.4, 0, 1)
    event = {
        "entity_id": entity_id,
        "failure_class": failure_class if failure_class != "normal" else None,
        "failure_timestamp": 1741234567.0,
        "window_start": 1741234567.0-3600,
        "window_end": 1741234567.0,
        "resource_series": metrics,
        "journal_series": [],
        "label": failure_class if failure_class != "normal" else None,
        "confidence": 1.0,
    }
    return event

def l3_generate_dataset_if_missing(
        output_path: str,
        num_entities: int = 4,
        per_class_count: dict = None,
        seed: int = 42):
    """
    Creates the output file ONLY if it doesn't exist already.
    """
    if os.path.exists(output_path):
        print(f"[L3] File exists, not overwriting: {output_path}")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if per_class_count is None:
        per_class_count = {c: 100 for c in FAILURE_CLASSES}
    np.random.seed(seed)
    entity_ids = [f"entity-{i+1}" for i in range(num_entities)]
    all_samples = []
    for fc in FAILURE_CLASSES:
        for i in range(per_class_count[fc]):
            entity_id = entity_ids[i % num_entities]
            sample = generate_synthetic_sample(entity_id, fc, seed=seed+i)
            all_samples.append(sample)
    np.random.shuffle(all_samples)
    meta = {
        "dataset_type": "synthetic",
        "class_balance": per_class_count,
        "entities": entity_ids,
    }
    with open(output_path, "w") as f:
        f.write("//META: "+json.dumps(meta)+"\n")
        for ev in all_samples:
            f.write(json.dumps(ev) + "\n")
    print(f"[L3] Dataset written: {output_path} | count: {len(all_samples)}")

# --- Main: Create ~4000-record datasets ---

if __name__ == "__main__":
    # Balanced: evenly split (round up for normal to get close to 4000)
    balanced_count = 572   # 572 * 7 = 4004
    balances = {
        "balanced": {c: balanced_count for c in FAILURE_CLASSES},
        "highly_imbalanced": {
            "normal": 3400,
            "cpu_overload": 120,
            "memory_exhaustion": 120,
            "storage_failure": 120,
            "network_downtime": 100,
            "service_crash": 80,
            "dependency_timeout": 60,
        }
    }

    l3_generate_dataset_if_missing("training_data/dataset_balanced.jsonl", per_class_count=balances["balanced"])
    l3_generate_dataset_if_missing("training_data/dataset_imbalanced.jsonl", per_class_count=balances["highly_imbalanced"])