import yaml
import httpx
import time
from collections import defaultdict
from ingestion.schema import ResourceRecord, JournalRecord, EntityMeta, EntityTelemetry
from pydantic import parse_obj_as

POLL_INTERVAL = 10  # seconds (adjust to match or undershoot your mock_server cadence)

def load_entities_from_config(cfg_path="config/connectors.yaml"):
    with open(cfg_path) as f:
        config = yaml.safe_load(f)
    entities = []
    for c in config['connectors']:
        for e in c.get('entities', []):
            entities.append((c['url'], e))
    return entities

def fetch_metrics(url, entity_id, start, end):
    r = httpx.get(f"{url}/metrics/data", params={"entity_id": entity_id, "start_ts": start, "end_ts": end}, timeout=5.0)
    r.raise_for_status()
    return r.json()

def fetch_logs(url, entity_id, start, end):
    r = httpx.get(f"{url}/journal/data", params={"entity_id": entity_id, "start_ts": start, "end_ts": end}, timeout=5.0)
    r.raise_for_status()
    return r.json()

def canonicalize_resource(rr):
    return ResourceRecord(
        entity_id=rr['entity_id'],
        source="mock",
        metric_type=rr['metric_type'],
        value=rr['value'],
        timestamp=rr['timestamp'],
        metadata=EntityMeta(**rr['metadata'])
    )

def canonicalize_journal(jr):
    return JournalRecord(
        entity_id=jr['entity_id'],
        source="mock",
        level=jr['level'],
        unit=jr['unit'],
        message=jr['message'],
        timestamp=jr['timestamp'],
        metadata=EntityMeta(**jr['metadata']),
        tags=jr.get('tags', {})
    )

def main():
    entities = load_entities_from_config()
    print(f"Loaded {len(entities)} entities, starting stream ingestion polling every {POLL_INTERVAL}s")
    last_ingested_ts = {}
    # For a fresh run, set start to "now - 60" so you never miss a window
    for _, e in entities:
        last_ingested_ts[e['id']] = int(time.time()) - POLL_INTERVAL

    while True:
        cycle_start = int(time.time())
        for url, e in entities:
            entity_id = e['id']
            meta = EntityMeta(**e['metadata'])
            start_ts = last_ingested_ts[entity_id]
            end_ts = int(time.time())
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
                print(f"[L0] {entity_id}: {len(resource_records)} new metrics, {len(journal_records)} new logs from t={start_ts} to {end_ts}")
                # Store/process your telemetry here, or pass to L1/L2, or append to file/db.

            last_ingested_ts[entity_id] = end_ts
        elapsed = int(time.time()) - cycle_start
        if elapsed < POLL_INTERVAL:
            time.sleep(POLL_INTERVAL - elapsed)
        # else, next poll starts immediately (if logic lags behind schedule)

if __name__ == "__main__":
    main()