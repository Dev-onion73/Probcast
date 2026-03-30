from typing import Optional, List, Dict
from statistics import mean

def sustained(resource, threshold, count=5):
    """True if resource exceeds threshold for ��count consecutive."""
    tally = 0
    for v in resource:
        if v > threshold:
            tally += 1
            if tally >= count:
                return True
        else:
            tally = 0
    return False

def cpu_overload_label(telemetry) -> Optional[Dict]:
    cpu = [r.value for r in telemetry.resource_records if r.metric_type == "cpu_usage"]
    logs = [j for j in telemetry.journal_records]
    if sustained(cpu, 0.85, count=5) and any(
        (j.level in ("ERROR", "CRITICAL") and (
            "soft lockup" in j.message.lower() or "watchdog" in j.message.lower())
        ) for j in logs
    ):
        anchor = max(
            (j for j in logs if "cpu overload" in j.message.lower()),
            key=lambda x: x.timestamp,
            default=None
        )
        if anchor:
            return dict(
                failure_class="cpu_overload",
                failure_timestamp=anchor.timestamp,
                confidence=0.95,
                anchor_log=anchor
            )
    return None

def memory_exhaustion_label(telemetry) -> Optional[Dict]:
    mem = [r.value for r in telemetry.resource_records if r.metric_type == "memory_usage"]
    logs = [j for j in telemetry.journal_records]
    if sustained(mem, 0.85, count=5) and any(
        (j.level in ("ERROR", "CRITICAL") and (
            "oom" in j.message.lower() or "killed" in j.message.lower())
        ) for j in logs
    ):
        anchor = max(
            (j for j in logs if "memory exhaustion" in j.message.lower()),
            key=lambda x: x.timestamp,
            default=None
        )
        if anchor:
            return dict(
                failure_class="memory_exhaustion",
                failure_timestamp=anchor.timestamp,
                confidence=0.93,
                anchor_log=anchor
            )
    return None

def storage_failure_label(telemetry) -> Optional[Dict]:
    disk_read = [r.value for r in telemetry.resource_records if r.metric_type == "disk_io_read"]
    disk_write = [r.value for r in telemetry.resource_records if r.metric_type == "disk_io_write"]
    logs = [j for j in telemetry.journal_records]
    # disk_io_read > 0.90 or collapse in write >50%
    read_anomaly = sustained(disk_read, 0.90, 2)
    write_collapse = (max(disk_write or [0]) > 0.05 and min(disk_write or [1]) < 0.01)
    has_anchor = any(j.level == "CRITICAL" and "storage failure" in j.message.lower() for j in logs)
    if (read_anomaly or write_collapse) and has_anchor:
        anchor = max(
            (j for j in logs if "storage failure" in j.message.lower()),
            key=lambda x: x.timestamp,
            default=None
        )
        if anchor:
            return dict(
                failure_class="storage_failure",
                failure_timestamp=anchor.timestamp,
                confidence=0.92,
                anchor_log=anchor
            )
    return None

def network_downtime_label(telemetry) -> Optional[Dict]:
    rx = [r.value for r in telemetry.resource_records if r.metric_type == "network_rx"]
    tx = [r.value for r in telemetry.resource_records if r.metric_type == "network_tx"]
    logs = [j for j in telemetry.journal_records]
    # Both rx and tx < 0.05 for 3+ intervals
    tally = 0
    for r, t in zip(rx, tx):
        if r < 0.05 and t < 0.05:
            tally += 1
            if tally >= 3:
                break
        else:
            tally = 0
    else:
        return None
    has_anchor = any(j.level == "CRITICAL" and "network downtime" in j.message.lower() for j in logs)
    if has_anchor:
        anchor = max(
            (j for j in logs if "network downtime" in j.message.lower()),
            key=lambda x: x.timestamp,
            default=None
        )
        if anchor:
            return dict(
                failure_class="network_downtime",
                failure_timestamp=anchor.timestamp,
                confidence=0.94,
                anchor_log=anchor
            )
    return None

def service_crash_label(telemetry) -> Optional[Dict]:
    # Cliff-edge detection for 'service_up' (drops from 1.0 to 0.0)
    sups = [r.value for r in telemetry.resource_records if r.metric_type == "service_up"]
    logs = [j for j in telemetry.journal_records]
    for i in range(1, len(sups)):
        if sups[i-1] == 1.0 and sups[i] == 0.0:
            # Look for systemd/service anchor
            has_anchor = any(j.level == "CRITICAL" and "service crashed" in j.message.lower() for j in logs)
            if has_anchor:
                anchor = max(
                    (j for j in logs if "service crashed" in j.message.lower()),
                    key=lambda x: x.timestamp,
                    default=None
                )
                if anchor:
                    return dict(
                        failure_class="service_crash",
                        failure_timestamp=anchor.timestamp,
                        confidence=0.93,
                        anchor_log=anchor
                    )
    return None

def dependency_timeout_label(telemetry) -> Optional[Dict]:
    latency = [r.value for r in telemetry.resource_records if r.metric_type == "probe_latency"]
    logs = [j for j in telemetry.journal_records]
    # Latency >0.90, anchor phrase
    if any(l > 0.90 for l in latency):
        has_anchor = any(j.level == "CRITICAL" and "dependency timeout" in j.message.lower() for j in logs)
        if has_anchor:
            anchor = max(
                (j for j in logs if "dependency timeout" in j.message.lower()),
                key=lambda x: x.timestamp,
                default=None
            )
            if anchor:
                return dict(
                    failure_class="dependency_timeout",
                    failure_timestamp=anchor.timestamp,
                    confidence=0.93,
                    anchor_log=anchor
                )
    return None

ALL_LABEL_FUNCTIONS = [
    cpu_overload_label,
    memory_exhaustion_label,
    storage_failure_label,
    network_downtime_label,
    service_crash_label,
    dependency_timeout_label
]