from typing import List, Dict
from ingestion.schema import ResourceRecord, SourceType, MetricType, EntityMeta
from ingestion.schema import JournalRecord, SourceType, JournalLevel, EntityMeta

def normalize_journal_records(raws):
    records = []
    for r in raws:
        meta = r["metadata"] if isinstance(r["metadata"], dict) else r.metadata
        records.append(JournalRecord(
            entity_id=r["entity_id"],
            source=SourceType.JOURNAL,
            level=JournalLevel(r["level"]),
            unit=r["unit"],
            message=r["message"],
            timestamp=r["timestamp"],
            metadata=EntityMeta(**meta),
            tags=r.get("tags", {})
        ))
    return records

def normalize_prometheus_records(raws: List[dict]) -> List[ResourceRecord]:
    records = []
    for r in raws:
        # Already in canonical format in this demo; in real: parse dictionary keys/structure here.
        meta = r["metadata"] if isinstance(r["metadata"], dict) else r.metadata
        records.append(ResourceRecord(
            entity_id=r["entity_id"],
            source=SourceType.PROMETHEUS,
            metric_type=MetricType(r["metric_type"]),
            value=r["value"],
            timestamp=r["timestamp"],
            metadata=EntityMeta(**meta)
        ))
    return records

