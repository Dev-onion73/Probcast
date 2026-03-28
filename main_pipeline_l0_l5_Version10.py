import os
import time
import yaml
import json
import asyncio
from pathlib import Path
from collections import Counter, defaultdict

from rich.console import Console
from rich.table import Table

import torch  # For model checkpoint save/load (Pyro+Torch)
from ingestion.aggregator import poll_connectors
from ingestion.normalizer import normalize_prometheus_records, normalize_journal_records
from ingestion.schema import EntityTelemetry
from hierarchy.encoder import infer_hierarchy
from hierarchy.matrix import build_aggregation_matrix
from hierarchy.pooling import partial_pooling_weights

# Import ALL labelers
from labelling.functions import (
    label_cpu_overload,
    label_memory_exhaustion,
    label_storage_failure,
    label_network_downtime,
    label_service_crash,
    label_dependency_timeout,
)
from labelling.output import LabeledEvent

import models._probcast_dual_model_fusion_Version1 as fusion_model

CONFIG_PATH = "config/connectors.yaml"
LABEL_OUT_DIR = "data/labeled"
MODEL_PATH = "models/fusion_model.pt"
MIN_PER_CLASS = 50  # adjust as needed

console = Console()

FAILURE_CLASSES = [
    "cpu_overload", "memory_exhaustion", "storage_failure",
    "network_downtime", "service_crash", "dependency_timeout", "normal"
]
ALL_LABELERS = [
    label_cpu_overload,
    label_memory_exhaustion,
    label_storage_failure,
    label_network_downtime,
    label_service_crash,
    label_dependency_timeout,
]

def check_fusion_model_exists():
    return os.path.exists(MODEL_PATH)

def save_fusion_model(model):
    Path(MODEL_PATH).parent.mkdir(exist_ok=True, parents=True)
    torch.save(model, MODEL_PATH)

def load_fusion_model():
    return torch.load(MODEL_PATH)

def check_connector_status(cfg) -> dict:
    import httpx
    status = {}
    for conn in cfg['connectors']:
        try:
            resp = httpx.get(f"{conn['url']}/health", timeout=2.5)
            status[conn['id']] = resp.status_code == 200
        except Exception:
            status[conn['id']] = False
    return status

def print_connector_status(status, config):
    console.rule("[bold cyan]Connector Status[/bold cyan]")
    for conn in config['connectors']:
        name = conn['id']
        meta = conn.get('entities', [{}])[0].get('metadata', {})  # Just first in group
        pretty = ', '.join(f"{k}:{v}" for k,v in meta.items()) if meta else "(no meta)"
        ok = status.get(name, False)
        icon = "[green]UP[/green]" if ok else "[red]DOWN[/red]"
        console.print(f"{icon} [bold]{name}[/bold] — {pretty}")

def enough_labels(counter: Counter, min_per_class: int, classes=None) -> bool:
    if not classes:
        return all(v >= min_per_class for k, v in counter.items())
    return all(counter.get(c, 0) >= min_per_class for c in classes)

# --- Main labeled event construction ---
def build_labeled_event(telem: EntityTelemetry, hierarchy: dict, pool_context: dict) -> LabeledEvent:
    # Apply all labelers, pick highest-confidence fire; if none, label="normal"
    results = []
    for fn in ALL_LABELERS:
        try:
            res = fn(telem)
            if res:
                results.append(res)
        except Exception as e:
            print(f"[WARN] Labeler {fn.__name__} on {telem.entity_id}: {e}")
    if results:
        best = max(results, key=lambda x: x.confidence)
        label = best.class_name
        confidence = best.confidence
        failure_ts = best.failure_timestamp
        window_start = failure_ts - 3600
        window_end = failure_ts
    else:
        label = "normal"
        confidence = 0.99
        failure_ts = None
        now = max([getattr(r, 'timestamp', 0) for r in telem.resource_records] + [0])
        window_start = now - 3600
        window_end = now
    metrics = set(getattr(r, 'metric_type', None) for r in telem.resource_records if hasattr(r, 'metric_type'))
    resource_series = {str(m): [r.value for r in telem.resource_records if r.metric_type == m] for m in metrics if m}
    journal_series = [
        {
            "offset_seconds": int(j.timestamp - window_start),
            "level": j.level,
            "unit": j.unit,
            "message": j.message,
        } for j in telem.journal_records if window_start <= j.timestamp <= window_end
    ]
    return LabeledEvent(
        entity_id=telem.entity_id,
        failure_class=None if label == "normal" else label,
        failure_timestamp=failure_ts,
        window_start=window_start,
        window_end=window_end,
        hierarchy=hierarchy,
        pool_context=pool_context,
        resource_series=resource_series,
        journal_series=journal_series,
        label=label,
        confidence=confidence
    )

def gather_and_label_balanced_dataset(cfg, min_per_class=MIN_PER_CLASS):
    label_counts = Counter()
    labeled_events = []
    console.rule("[bold yellow]Balanced Dataset Construction[/bold yellow]")
    console.print("Collecting labeled windows until class balance achieved...")
    while True:
        now = time.time()
        t0 = now - 3600  # 1h window; widen if few failures detected
        raw = asyncio.run(poll_connectors(cfg["connectors"], t0, now))
        prom = [r for r in raw if hasattr(r, 'source') and r.source in ("prometheus", "cloudwatch")]
        journ = [r for r in raw if hasattr(r, 'source') and r.source == "journal"]
        ent_resource = defaultdict(list)
        ent_journal = defaultdict(list)
        for r in prom:
            ent_resource[r.entity_id].append(r)
        for j in journ:
            ent_journal[j.entity_id].append(j)
        entities = []
        entity_ids = set(ent_resource) | set(ent_journal)
        # DEBUGGING: show record counts for first few entities
        for eid in list(entity_ids)[:5]:
            print(f"\nDBG ENTITY {eid}: {len(ent_resource[eid])} resource, {len(ent_journal[eid])} journal")
            if len(ent_resource[eid]) and len(ent_journal[eid]):
                print("Sample resource ts:", [r.timestamp for r in ent_resource[eid]][:3])
                print("Sample journal ts:", [j.timestamp for j in ent_journal[eid]][:3])
        for eid in entity_ids:
            meta = (ent_resource[eid][0].metadata if ent_resource[eid]
                    else ent_journal[eid][0].metadata if ent_journal[eid] else None)
            te = EntityTelemetry(
                entity_id=eid,
                metadata=meta,
                resource_records=ent_resource[eid],
                journal_records=ent_journal[eid],
            )
            if not te.has_both_streams:
                continue
            entities.append(te)
        # L1: Dynamic hierarchy stats (optional, fast)
        hierarchies = {}
        meta_list = [e.metadata for e in entities if e.metadata]
        poolings = {}
        if meta_list:
            tree = infer_hierarchy(meta_list)
            S_matrix, entity_ids_list, group_ids = build_aggregation_matrix(tree)
            pooling_stats = partial_pooling_weights(entities, group_ids)
            for e in entities:
                hierarchies[e.entity_id] = {
                    "host": getattr(e.metadata, "host", ""),
                    "subnet": getattr(e.metadata, "subnet", ""),
                    "environment": getattr(e.metadata, "environment", ""),
                    "org": getattr(e.metadata, "org", ""),
                }
            poolings = {e.entity_id: {} for e in entities}
        # L2: Labelling
        for ent in entities:
            lab = build_labeled_event(ent, hierarchies.get(ent.entity_id, {}), poolings.get(ent.entity_id, {}))
            labeled_events.append(lab)
            label_counts[lab.label] += 1
        # Print progress
        console.print({k: label_counts[k] for k in FAILURE_CLASSES})
        if enough_labels(label_counts, min_per_class, FAILURE_CLASSES):
            break
        time.sleep(3)
    Path(LABEL_OUT_DIR).mkdir(exist_ok=True, parents=True)
    out_path = os.path.join(LABEL_OUT_DIR, "balanced_labeled_events.jsonl")
    with open(out_path, "w") as f:
        for ev in labeled_events:
            f.write(json.dumps(ev.__dict__) + "\n")
    console.print(f"[bold green]Exported balanced dataset to {out_path}[/bold green]")
    return out_path

def train_fusion_model_on_dataset(dataset_path):
    with open(dataset_path) as f:
        labeled_events = [json.loads(line) for line in f]
    console.rule("[bold magenta]Model Training (L4/L5)[/bold magenta]")
    model = fusion_model.train_on_labeled_events(labeled_events)
    save_fusion_model(model)
    console.print(f"[bold green]Fusion model saved to {MODEL_PATH}[/bold green]")
    return model

def run_live_monitoring(model, cfg):
    console.rule("[bold cyan]Live Monitoring & Inference[/bold cyan]")
    console.print("Polling connectors for real-time inference. Ctrl+C to exit.")
    while True:
        now = time.time()
        t0 = now - 3600
        raw = asyncio.run(poll_connectors(cfg["connectors"], t0, now))
        prom = [r for r in raw if hasattr(r, 'source') and r.source in ("prometheus", "cloudwatch")]
        journ = [r for r in raw if hasattr(r, 'source') and r.source == "journal"]
        ent_resource = defaultdict(list)
        ent_journal = defaultdict(list)
        for r in prom:
            ent_resource[r.entity_id].append(r)
        for j in journ:
            ent_journal[j.entity_id].append(j)
        entities = []
        eid_set = set(ent_resource) | set(ent_journal)
        for eid in eid_set:
            meta = ent_resource[eid][0].metadata if ent_resource[eid] else ent_journal[eid][0].metadata
            te = EntityTelemetry(
                entity_id=eid,
                metadata=meta,
                resource_records=ent_resource[eid],
                journal_records=ent_journal[eid],
            )
            if not te.has_both_streams:
                continue
            entities.append(te)
        # Run model inference (result is per-entity risk vector)
        results = []
        for ent in entities:
            res = fusion_model.predict(model, ent)  # <--- ensure model .predict works this way!
            results.append((ent.entity_id, res))
        # Display as table
        tab = Table(title="Probabilistic Failure Forecast")
        tab.add_column("Entity")
        tab.add_column("Probabilities (per class)")
        for eid, res in results:
            tab.add_row(eid, str(res))
        console.print(tab)
        time.sleep(10)

def main():
    if not Path(CONFIG_PATH).exists():
        console.print(f"[bold red]Config file not found: {CONFIG_PATH}")
        exit(1)
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    status = check_connector_status(cfg)
    print_connector_status(status, cfg)
    if not all(status.values()):
        console.print("[bold red]Some connectors are down. Start all required connectors before running pipeline.[/bold red]")
        exit(1)
    if not check_fusion_model_exists():
        dataset_path = gather_and_label_balanced_dataset(cfg, min_per_class=MIN_PER_CLASS)
        model = train_fusion_model_on_dataset(dataset_path)
    else:
        model = load_fusion_model()
        console.print(f"[bold yellow]Loaded pre-trained model from {MODEL_PATH}[/bold yellow]")
    run_live_monitoring(model, cfg)

if __name__ == "__main__":
    main()