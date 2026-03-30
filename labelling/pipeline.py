import json
from labelling.functions import ALL_LABEL_FUNCTIONS # see your prior L2 answer
from ingestion.schema import EntityTelemetry
from ingestion.ingest_and_normalize import ingest_entities # assume you have this

def label_entity(telemetry: EntityTelemetry):
    results = []
    for fn in ALL_LABEL_FUNCTIONS:
        label = fn(telemetry)
        if label:
            results.append(label)
    if results:
        results.sort(key=lambda x: (x['confidence'], x['failure_timestamp']), reverse=True)
        return results[0]
    return None

def extract_window(resource_records, journal_records, anchor_ts, lookback_sec=3600):
    window_start = anchor_ts - lookback_sec
    rr = [r for r in resource_records if window_start <= r.timestamp <= anchor_ts]
    jr = [j for j in journal_records if window_start <= j.timestamp <= anchor_ts]
    return rr, jr, window_start, anchor_ts

def labeled_event_format(entity_id, meta, label, resource_records, journal_records):
    rr_by_metric = {}
    for r in resource_records:
        rr_by_metric.setdefault(r.metric_type, []).append(r.value)
    jr_serialized = []
    for j in journal_records:
        jr_serialized.append({
            "offset_seconds": int(j.timestamp - label['failure_timestamp']),
            "level": j.level,
            "unit": j.unit,
            "message": j.message
        })
    return {
        "entity_id": entity_id,
        "failure_class": label["failure_class"] if label else None,
        "failure_timestamp": label["failure_timestamp"] if label else None,
        "window_start": min(r.timestamp for r in resource_records) if resource_records else None,
        "window_end": max(r.timestamp for r in resource_records) if resource_records else None,
        "hierarchy": {
            "host": meta.host,
            "subnet": meta.subnet,
            "environment": meta.environment,
            "org": meta.org
        },
        "resource_series": rr_by_metric,
        "journal_series": jr_serialized,
        "label": label["failure_class"] if label else None,
        "confidence": label["confidence"] if label else None,
    }

def run_labelling_pipeline():
    window_minutes = 5               # Window for precursor + anchor
    entities = list(ingest_entities(window_minutes=window_minutes))
    output = []
    for t in entities:
        label = label_entity(t)
        if label:
            rr_w, jr_w, window_start, window_end = extract_window(
                t.resource_records, t.journal_records, label['failure_timestamp'], lookback_sec=window_minutes*60
            )
            event = labeled_event_format(
                t.entity_id, t.metadata, label, rr_w, jr_w
            )
            output.append(event)
            print(f"[L2] Entity {t.entity_id}: label={label['failure_class']} at t={label['failure_timestamp']}")
        else:
            print(f"[L2] Entity {t.entity_id}: normal regime (no label)")
    # Write to file
    with open("data/labeled/l2_labeled_events.jsonl", "w") as f:
        for obj in output:
            f.write(json.dumps(obj) + "\n")
    print(f"Wrote {len(output)} labeled events to data/labeled/l2_labeled_events.jsonl")

if __name__ == "__main__":
    run_labelling_pipeline()