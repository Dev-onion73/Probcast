import os
import time
import yaml
import json
import torch
import numpy as np
from pathlib import Path

from ingestion.continuous_ingest import (
    load_entities_from_config,
    fetch_metrics,
    fetch_logs,
    canonicalize_resource,
    canonicalize_journal
)
from ingestion.schema import EntityTelemetry, EntityMeta

from hierarchy_encoder_matrix import get_hierarchy_model_inputs
from label_detection import (
    load_anchor_messages,
    probe_failure_labels,
    load_entities as load_label_entities,
)
from models.deep_poisson import SimpleMLP

# Configurable paths/params
MODEL_PATH_B = "outputs/pathB_deep_poisson.pt"
CONFIG_PATH = "config/connectors.yaml"
REGIME_CONFIG = "config/regimes.yaml"
OUTPUT_PREDICTIONS = "outputs/latest_preds.json"
OUTPUT_LABELS = "outputs/latest_labels.json"
OUTPUT_STATUS = "outputs/latest_status.json"
OUTPUT_HIERARCHY = "outputs/latest_hierarchy.json"
POLL_INTERVAL = 60  # seconds

DELTA_T_LIST = [90*24*60*60, 180*24*60*60, 365*24*60*60]  # 90d, 180d, 365d

def load_modelB():
    checkpoint_b = torch.load(MODEL_PATH_B, map_location="cpu")
    meta_b = checkpoint_b.get("meta", {})
    saved_input_dim = meta_b.get("input_dim", 0)
    n_classes = len(meta_b["FAILURE_CLASSES"])
    # Infer real input_dim from checkpoint if meta is wrong
    real_input_dim = None
    try:
        sd = checkpoint_b["state_dict"]
        for k in sd:
            if k.endswith("seq.0.weight"):
                real_input_dim = sd[k].shape[1]
                break
    except Exception:
        pass
    input_dim = real_input_dim if (real_input_dim and real_input_dim > 0) else saved_input_dim
    if input_dim == 0 or input_dim is None:
        raise RuntimeError("Could not determine input_dim for SimpleMLP from checkpoint or meta. Please check/export model again.")
    if saved_input_dim != input_dim:
        print(f"[backend:WARN] Meta input_dim={saved_input_dim}, checkpoint weights expect {input_dim}; using {input_dim}.")
    model_b = SimpleMLP(input_dim, n_classes)
    model_b.load_state_dict(checkpoint_b["state_dict"])
    model_b.eval()
    meta_b["input_dim"] = input_dim
    return model_b, meta_b

def prepare_features_pathB(entities, meta_b):
    all_metrics = meta_b.get("METRIC_KEYS")
    if not all_metrics:
        all_metrics = sorted({
            k for ent in entities for k in ent.resource_summary().keys()
        })
    feature_dim = meta_b["input_dim"]
    X = []
    for ent in entities:
        summary = ent.resource_summary()
        feats = []
        for k in all_metrics:
            arr = summary[k].get("window", []) if k in summary else []
            arr = arr if arr else [summary[k]["mean"]]*10 if k in summary else [0.0]*10
            feats.append(summary[k]["mean"] if k in summary else 0.0)
            feats.append(summary[k]["std"] if k in summary else 0.0)
            feats.extend(arr[:10])
        feats = feats[:feature_dim] if len(feats) >= feature_dim else feats + [0.0]*(feature_dim-len(feats))
        X.append(np.array(feats, dtype=np.float32))
    if len(X) > 0 and feature_dim > 0:
        return np.stack(X)
    return np.zeros((0, feature_dim), dtype=np.float32)

def run_pathB_inference(entities, model_b, meta_b, delta_t_s):
    X_b = prepare_features_pathB(entities, meta_b)
    num_classes = len(meta_b["FAILURE_CLASSES"])
    if X_b.shape[0]:
        with torch.no_grad():
            logits = model_b(torch.tensor(X_b))
            pb_probmat = torch.softmax(logits, dim=1).numpy()
    else:
        pb_probmat = np.zeros((len(entities), num_classes))
    results = []
    for idx, ent in enumerate(entities):
        row = {
            "entity_id": ent.entity_id,
            "host": getattr(ent.metadata, "host", ""),
            "subnet": getattr(ent.metadata, "subnet", ""),
            "delta_t_seconds": delta_t_s,
            "probs_per_class": {meta_b["FAILURE_CLASSES"][c]: float(pb_probmat[idx, c]) for c in range(num_classes)},
            "raw_pathB": {meta_b["FAILURE_CLASSES"][c]: float(pb_probmat[idx, c]) for c in range(num_classes)},
        }
        results.append(row)
    return results

def ingest_entities(cfg_path=CONFIG_PATH, poll_interval=POLL_INTERVAL):
    entities = load_entities_from_config(cfg_path)
    last_ingested_ts = {e['id']: int(time.time()) - poll_interval for _, e in entities}
    while True:
        window = []
        for url, e in entities:
            entity_id = e['id']
            meta = EntityMeta(**e['metadata'])
            start_ts = last_ingested_ts[entity_id]
            end_ts = int(time.time())
            try:
                metrics_raw = fetch_metrics(url, entity_id, start_ts, end_ts)
                logs_raw = fetch_logs(url, entity_id, start_ts, end_ts)
                resource_records = [canonicalize_resource(r) for r in metrics_raw]
                journal_records = [canonicalize_journal(j) for j in logs_raw]
                telemetry = EntityTelemetry(
                    entity_id=entity_id,
                    metadata=meta,
                    resource_records=resource_records,
                    journal_records=journal_records,
                )
                if telemetry.has_both_streams:
                    window.append(telemetry)
            except Exception as ex:
                print(f"[backend:L0] failed to fetch or parse for entity {entity_id}: {ex}")
            last_ingested_ts[entity_id] = end_ts
        yield window
        time.sleep(poll_interval)

def main():
    print("== ProbCast Backend: L0→L2 PathB (Deep Poisson Only) Inference ==")
    model_b, meta_b = load_modelB()
    print("[backend] Path B model loaded and ready for inference.")

    # L1: static hierarchy
    hierarchy, S, hosts, subnets = get_hierarchy_model_inputs(CONFIG_PATH)
    out_h = {
        "tree": hierarchy,
        "matrix": S.tolist(),
        "hosts": hosts,
        "subnets": subnets
    }
    Path("outputs").mkdir(exist_ok=True)
    with open(OUTPUT_HIERARCHY, "w") as f:
        json.dump(out_h, f, indent=2)
    print("[backend] Exported current hierarchy snapshot.")

    # L2 setup
    anchor_phrases = load_anchor_messages(REGIME_CONFIG)
    entity_ids = load_label_entities(CONFIG_PATH)

    for entities in ingest_entities(CONFIG_PATH, POLL_INTERVAL):
        tick = int(time.time())
        try:
            print(f"\n[backend] Fetched {len(entities)} paired entities for L0 telemetry this poll window.")
            if not entities:
                print("[backend] No eligible entities this poll, sleeping.")
                continue

            # L2 labelling probe (optional, for UI/monitoring)
            found_per_entity, found_by_class = probe_failure_labels(
                entity_ids, "http://localhost:8101", anchor_phrases, window_seconds=600
            )
            latest_labels = []
            for eid in entity_ids:
                labels = sorted(list(found_per_entity.get(eid, set())))
                latest_labels.append({
                    "entity_id": eid,
                    "detected_labels": labels,
                })
            with open(OUTPUT_LABELS, "w") as f:
                json.dump(latest_labels, f, indent=2)

            # For each horizon, run model inference (Path B only)
            all_preds = []
            for delta_t in DELTA_T_LIST:
                preds = run_pathB_inference(
                    entities, model_b, meta_b, delta_t
                )
                for row in preds:
                    row['forecast_horizon'] = f"{delta_t//(24*60*60)}d"
                all_preds.extend(preds)
            with open(OUTPUT_PREDICTIONS, "w") as f:
                json.dump(all_preds, f, indent=2)

            status = {
                "timestamp": tick,
                "entity_count": len(entities)
            }
            with open(OUTPUT_STATUS, "w") as f:
                json.dump(status, f, indent=2)

            print(f"[backend] Wrote hierarchy, labels, {len(all_preds)} model preds, status. Sleeping for next poll window.")
        except Exception as e:
            print("[backend] ERROR:", e)

if __name__ == "__main__":
    main()