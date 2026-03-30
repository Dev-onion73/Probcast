import yaml
import httpx
from typing import List, Dict
from ingestion.schema import ResourceRecord, JournalRecord, EntityMeta, EntityTelemetry
from pydantic import parse_obj_as
from datetime import datetime, timedelta

COMBINED_MOCK_URL = "http://localhost:8101"  # or read from your config

def load_entities_from_config(cfg_path="config/connectors.yaml") -> List[Dict]:
    with open(cfg_path) as f:
        config = yaml.safe_load(f)
    entities = []
    for c in config['connectors']:
        for e in c.get('entities', []):
            entities.append((c['url'], e))
    return entities

def fetch_metrics(url: str, entity_id: str, start: float, end: float):
    r = httpx.get(
        f"{url}/metrics/data",
        params={"entity_id": entity_id, "start_ts": start, "end_ts": end},
        timeout=10.0)
    r.raise_for_status()
    return r.json()

def fetch_logs(url: str, entity_id: str, start: float, end: float):
    r = httpx.get(
        f"{url}/journal/data",
        params={"entity_id": entity_id, "start_ts": start, "end_ts": end},
        timeout=10.0)
    r.raise_for_status()
    return r.json()

def canonicalize_resource(rr) -> ResourceRecord:
    return ResourceRecord(
        entity_id=rr['entity_id'],
        source="mock",
        metric_type=rr['metric_type'],
        value=rr['value'],
        timestamp=rr['timestamp'],
        metadata=EntityMeta(**rr['metadata'])
    )

def canonicalize_journal(jr) -> JournalRecord:
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

def ingest_entities(window_minutes=60):
    entities = load_entities_from_config()
    now = datetime.utcnow().timestamp()
    start_ts = now - window_minutes * 60
    end_ts = now

    for url, e in entities:
        entity_id = e['id']
        meta = EntityMeta(**e['metadata'])
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
        # Only yield if both streams present
        if telemetry.has_both_streams:
            yield telemetry

if __name__ == "__main__":
    for telemetry in ingest_entities(window_minutes=120):
        print(f"L0 — Entity: {telemetry.entity_id} ({len(telemetry.resource_records)} metrics, {len(telemetry.journal_records)} logs)")