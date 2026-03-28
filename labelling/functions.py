from typing import Optional
from ingestion.schema import EntityTelemetry, JournalLevel
from dataclasses import dataclass
import re

@dataclass
class LabelResult:
    class_name: str
    failure_timestamp: float
    confidence: float

# Helper for string matching with noise and optional word boundary
def match_message(journal, pattern):
    return re.search(pattern, journal.message, re.IGNORECASE)

def label_cpu_overload(telem: EntityTelemetry) -> Optional[LabelResult]:
    # Resource: 5+ consecutive cpu_usage > 0.85
    streak, max_streak, streak_ts = 0, 0, None
    for r in telem.resource_records:
        if str(r.metric_type) == "cpu_usage" and r.value > 0.85:
            streak += 1
            if streak >= 5 and streak > max_streak:
                streak_ts = r.timestamp
                max_streak = streak
        else:
            streak = 0
    if not streak_ts:
        return None
    crits = [j for j in telem.journal_records
             if j.level in (JournalLevel.ERROR, JournalLevel.CRITICAL) and
                ("CPU" in j.message.upper() or match_message(j, r'soft lockup|watchdog|NMI|CPU overload'))]
    if not crits:
        return None
    anchor = max(crits, key=lambda j: j.timestamp)
    confidence = min(1.0, 0.7 + 0.05 * (max_streak-5) + 0.1 * len(crits))
    return LabelResult("cpu_overload", anchor.timestamp, confidence)

def label_memory_exhaustion(telem: EntityTelemetry) -> Optional[LabelResult]:
    # Resource: memory_usage > 0.85 AND swap > 0 sustained 5+ intervals
    mem_streak, swap_streak, ts = 0, 0, None
    for r in telem.resource_records:
        if str(r.metric_type) == "memory_usage" and r.value > 0.85:
            mem_streak += 1
        if str(r.metric_type) == "swap_usage" and r.value > 0:
            swap_streak += 1
    if mem_streak < 5 or swap_streak < 5:
        return None
    crits = [j for j in telem.journal_records
             if j.level in (JournalLevel.ERROR, JournalLevel.CRITICAL) and
                match_message(j, r'OOM|Out of memory|Killed process|SIGKILL|Memory exhaustion')]
    if not crits:
        return None
    anchor = max(crits, key=lambda j: j.timestamp)
    confidence = min(1.0, 0.7 + 0.02 * (mem_streak+swap_streak-10) + 0.1 * len(crits))
    return LabelResult("memory_exhaustion", anchor.timestamp, confidence)

def label_storage_failure(telem: EntityTelemetry) -> Optional[LabelResult]:
    # Resource: disk_io_read > 0.90 OR write collapse >50%
    r_streak, w_streak, r_peak = 0, 0, 0
    writes = [r.value for r in telem.resource_records if str(r.metric_type) == "disk_io_write"]
    if writes and writes[0] > 0:
        write_drop = (writes[0] - min(writes))/writes[0]
    else:
        write_drop = 0
    for r in telem.resource_records:
        if str(r.metric_type) == "disk_io_read" and r.value > 0.9:
            r_streak += 1
            if r.value > r_peak: r_peak = r.value
        if str(r.metric_type) == "disk_io_write" and write_drop > 0.5:
            w_streak += 1
    if r_streak < 3 and w_streak < 3:
        return None
    crits = [j for j in telem.journal_records
             if j.level in (JournalLevel.ERROR, JournalLevel.CRITICAL) and
                match_message(j, r'EXT4.*error|SCSI.*fail|device.*unresponsive|I/O error|superblock')]
    if not crits:
        return None
    anchor = max(crits, key=lambda j: j.timestamp)
    confidence = min(1.0, 0.6 + 0.1 * (r_streak+w_streak) + 0.1 * len(crits))
    return LabelResult("storage_failure", anchor.timestamp, confidence)

def label_network_downtime(telem: EntityTelemetry) -> Optional[LabelResult]:
    # Resource: network_rx < 0.05 AND network_tx < 0.05 for 3+ intervals
    rx_down, tx_down = 0, 0
    for r in telem.resource_records:
        if str(r.metric_type) == "network_rx" and r.value < 0.05:
            rx_down += 1
        if str(r.metric_type) == "network_tx" and r.value < 0.05:
            tx_down += 1
    if rx_down < 3 or tx_down < 3:
        return None
    crits = [j for j in telem.journal_records
             if j.level in (JournalLevel.ERROR, JournalLevel.CRITICAL) and
                match_message(j, r'carrier lost|interface down|Network downtime|no gateway|transmit queue timeout|Connectivity check failed')]
    if not crits:
        return None
    anchor = max(crits, key=lambda j: j.timestamp)
    confidence = min(1.0, 0.8 + 0.05 * min(rx_down, tx_down) + 0.1 * len(crits))
    return LabelResult("network_downtime", anchor.timestamp, confidence)

def label_service_crash(telem: EntityTelemetry) -> Optional[LabelResult]:
    # Resource: abrupt drop in request_rate (cliff)
    reqs = [(r.timestamp, r.value) for r in telem.resource_records if str(r.metric_type) == "request_rate"]
    if len(reqs) < 2:
        return None
    diffs = [reqs[i][1] - reqs[i+1][1] for i in range(len(reqs)-1)]
    if not diffs or max(diffs) < 0.1:  # Tunable: 10% drop minimum
        return None
    crits = [j for j in telem.journal_records
             if j.level in (JournalLevel.CRITICAL, JournalLevel.ERROR) and
                match_message(j, r'(service exited|Failed with result signal|Service crashed|timeout|main process exited)')]
    if not crits:
        return None
    anchor = max(crits, key=lambda j: j.timestamp)
    cliff_val = max(diffs)
    confidence = min(1.0, 0.7 + 0.3 * cliff_val + 0.1 * len(crits))
    return LabelResult("service_crash", anchor.timestamp, confidence)

def label_dependency_timeout(telem: EntityTelemetry) -> Optional[LabelResult]:
    # Resource: latency spike, not due to cpu/mem
    latencies = [r.value for r in telem.resource_records if str(r.metric_type) == "latency"]
    if len(latencies) > 4 and max(latencies) > 0.55:
        crits = [j for j in telem.journal_records
                 if j.level in (JournalLevel.CRITICAL, JournalLevel.ERROR) and
                    match_message(j, r'circuit breaker open|all retries exhausted|Dependency timeout|failed within SLA')]
        if not crits:
            return None
        anchor = max(crits, key=lambda j: j.timestamp)
        confidence = min(1.0, 0.6 + 0.2 * max(latencies) + 0.1 * len(crits))
        return LabelResult("dependency_timeout", anchor.timestamp, confidence)
    return None