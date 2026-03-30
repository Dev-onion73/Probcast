from typing import List
from ingestion.schema import ResourceRecord, SourceType, MetricType, EntityMeta, JournalRecord, JournalLevel

def normalize_prometheus_records(raws: List[dict]) -> List[ResourceRecord]:
    records = []
    for r in raws:
        meta = r["metadata"] if isinstance(r["metadata"], dict) else r.metadata
        records.append(ResourceRecord(
            entity_id   = r["entity_id"],
            source      = SourceType.PROMETHEUS,
            metric_type = MetricType(r["metric_type"]),
            value       = r["value"],
            timestamp   = r["timestamp"],
            metadata    = EntityMeta(**meta)
        ))
    return records

def normalize_journal_records(raws: List[dict]) -> List[JournalRecord]:
    records = []
    for r in raws:
        meta = r["metadata"] if isinstance(r["metadata"], dict) else r.metadata
        records.append(JournalRecord(
            entity_id   = r["entity_id"],
            source      = SourceType.JOURNAL,
            level       = JournalLevel(r["level"]),
            unit        = r["unit"],
            message     = r["message"],
            timestamp   = r["timestamp"],
            metadata    = EntityMeta(**meta),
            tags        = r.get("tags", {})
        ))
    return records