import os
import time
import yaml
import json
from pathlib import Path
from collections import Counter
import torch

# INGESTION & NORMALIZATION (functions only!)
from ingestion.aggregator import poll_connectors
from ingestion.normalizer import normalize_all
from ingestion.store import Store

# HIERARCHY
from hierarchy.encoder import infer_hierarchy
from hierarchy.matrix import build_aggregation_matrix
from hierarchy.pooling import build_pooling_structure

# LABELLING
from labelling.pipeline import label_events_for_entities

# L4/L5 – Your model file: must provide these functions
import models._probcast_dual_model_fusion_Version1 as fusion_model

# CONFIG
CONNECTOR_CONFIG_PATH = "config/connectors.yaml"
MODEL_PATH = "models/fusion_model.pt"
DATA_LABEL_DIR = "data/labeled/"
MIN_LABELS_PER_CLASS = 40

def model_exists():
    return os.path.exists(MODEL_PATH)

def save_fusion_model(model):
    Path(MODEL_PATH).parent.mkdir(exist_ok=True)
    torch.save(model, MODEL_PATH)

def load_fusion_model():
    return torch.load(MODEL_PATH)

def check_connectors_status(connector_config):
    import httpx
    statuses = {}
    for conn in connector_config["connectors"]:
        try:
            resp = httpx.get(f"{conn['url']}/health", timeout=2.5)
            statuses[conn['id']] = resp.status_code == 200
        except Exception:
            statuses[conn['id']] = False
    return statuses

def print_connectors_status(statuses):
    print("Connector Status:")
    for cid, up in statuses.items():
        print(f"  {cid:<20} {'[UP]' if up else '[DOWN]'}")

def enough_labels(counts, min_per_class=MIN_LABELS_PER_CLASS):
    return all(v >= min_per_class for k,v in counts.items() if k != 'normal')

def gather_and_label_balanced_dataset(connector_config, min_per_class=MIN_LABELS_PER_CLASS):
    store = Store()
    label_counts = Counter()
    labeled_events = []

    print("[DATA GATHER]: Collecting labeled windows until balance per class...")
    while True:
        # Pull raw from all connectors (function, not class)
        raw_records = poll_connectors(connector_config)
        normalized = normalize_all(raw_records)
        store.ingest(normalized)
        entities = store.get_all_entity_telemetry()
        ready = [e for e in entities if (e.has_both_streams if hasattr(e, "has_both_streams") else e.has_both_streams())]
        if not ready:
            time.sleep(4)
            continue
        hierarchy = infer_hierarchy([e.metadata for e in ready])
        S = build_aggregation_matrix(hierarchy)
        pooling = {e.entity_id: build_pooling_structure(e, hierarchy) for e in ready}
        lab_windows = label_events_for_entities(ready, pooling)
        labeled_events.extend(lab_windows)
        label_counts.update(event['label'] for event in lab_windows if event.get('label'))
        print({k: v for k, v in sorted(label_counts.items())})
        if enough_labels(label_counts, min_per_class):
            print("Balanced dataset achieved!")
            break
        time.sleep(4)
    Path(DATA_LABEL_DIR).mkdir(exist_ok=True, parents=True)
    out_path = os.path.join(DATA_LABEL_DIR, "balanced_labeled_events.jsonl")
    with open(out_path, "w") as f:
        for event in labeled_events:
            f.write(json.dumps(event))
            f.write("\n")
    print(f"Labeled data exported to {out_path}")
    return labeled_events

def train_fusion_model_on_dataset():
    data_path = os.path.join(DATA_LABEL_DIR, "balanced_labeled_events.jsonl")
    with open(data_path) as f:
        labeled_events = [json.loads(line) for line in f]
    print("[TRAINING] Training fusion model...")
    model = fusion_model.train_on_labeled_events(labeled_events)
    save_fusion_model(model)
    print("[TRAINING] Model saved.")
    return model

def start_monitoring_and_inference(model, connector_config):
    store = Store()
    print("[MONITORING] Live forecasting started. Press Ctrl+C to exit.")
    try:
        while True:
            raw_records = poll_connectors(connector_config)
            normalized = normalize_all(raw_records)
            store.ingest(normalized)
            entities = store.get_all_entity_telemetry()
            ready = [e for e in entities if (e.has_both_streams if hasattr(e, "has_both_streams") else e.has_both_streams())]
            results = []
            for e in ready:
                result = fusion_model.predict(model, e)
                results.append(result)
            print("[LIVE FORECAST]")
            for r in results:
                entity = r.get('entity_id') or 'unknown'
                label_probs = r.get('probabilities', r)
                print(f"{entity}: {label_probs}")
            time.sleep(10)
    except KeyboardInterrupt:
        print("Stopped monitoring.")

if __name__ == "__main__":
    print("========== ProbCast Unified L0-L5 Pipeline ==========")
    with open(CONNECTOR_CONFIG_PATH) as f:
        connector_config = yaml.safe_load(f)

    status = check_connectors_status(connector_config)
    print_connectors_status(status)
    if not all(status.values()):
        print("Some connectors are down. Start all required connectors.")
        exit(1)

    if model_exists():
        model = load_fusion_model()
        print("[INFO] Found pre-trained fusion model.")
    else:
        labeled_events = gather_and_label_balanced_dataset(connector_config)
        model = train_fusion_model_on_dataset()

    start_monitoring_and_inference(model, connector_config)