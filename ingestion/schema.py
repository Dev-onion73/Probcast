from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional

class SourceType(str, Enum):
    PROMETHEUS = "prometheus"
    JOURNAL = "journal"
    CLOUDWATCH = "cloudwatch"
    SIEM = "siem"

class MetricType(str, Enum):
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_IO_READ = "disk_io_read"
    DISK_IO_WRITE = "disk_io_write"
    NETWORK_RX = "network_rx"
    NETWORK_TX = "network_tx"
    SERVICE_UP = "service_up"
    PROBE_LATENCY = "probe_latency"

class JournalLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class EntityMeta:
    host: str
    subnet: str
    environment: str
    org: str

@dataclass
class ResourceRecord:
    entity_id: str
    source: SourceType
    metric_type: MetricType
    value: float
    timestamp: float
    metadata: EntityMeta

@dataclass
class JournalRecord:
    entity_id: str
    source: SourceType
    level: JournalLevel
    unit: str
    message: str
    timestamp: float
    metadata: EntityMeta
    tags: Dict

@dataclass
class EntityTelemetry:
    entity_id: str
    metadata: EntityMeta
    resource_records: List[ResourceRecord]
    journal_records: List[JournalRecord]

    @property
    def has_both_streams(self) -> bool:
        return bool(self.resource_records) and bool(self.journal_records)

    def resource_summary(self) -> Dict[str, Dict[str, float]]:
        import numpy as np
        ret = {}
        by_metric = {}
        for rec in self.resource_records:
            by_metric.setdefault(rec.metric_type, []).append(rec.value)
        for typ, vals in by_metric.items():
            ret[typ] = {
                "min": float(np.min(vals)),
                "mean": float(np.mean(vals)),
                "max": float(np.max(vals))
            }
        return ret

    def journal_summary(self) -> Dict[str, int]:
        d = {}
        for rec in self.journal_records:
            d[rec.level] = d.get(rec.level, 0) + 1
        return d