from typing import Optional
from ingestion.schema import EntityTelemetry, JournalLevel
from dataclasses import dataclass

@dataclass
class LabelResult:
    class_name: str
    failure_timestamp: float
    confidence: float

def label_cpu_overload(telem: EntityTelemetry) -> Optional[LabelResult]:
    # 1. Find 5+ consecutive cpu_usage > 0.85
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
    # 2. At least one ERROR+ journal event with "CPU" in message
    crits = [j for j in telem.journal_records
             if j.level in (JournalLevel.ERROR, JournalLevel.CRITICAL) and "CPU" in j.message.upper()]
    if not crits:
        return None
    # Failure timestamp = latest relevant journal
    anchor = max(crits, key=lambda j: j.timestamp)
    confidence = min(1.0, 0.7 + 0.1 * (max_streak-5))
    return LabelResult("cpu_overload", anchor.timestamp, confidence)