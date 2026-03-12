from labelling.functions import label_cpu_overload
from labelling.output import LabeledEvent
from ingestion.schema import EntityTelemetry
from typing import List
import json
import os

def label_entity(telem: EntityTelemetry, hierarchy, pool_context) -> LabeledEvent:
    result = label_cpu_overload(telem)
    # (Add more label funcs and resolve per Section 8.4)
    if result:
        label = result.class_name
        confidence = result.confidence
        failure_ts = result.failure_timestamp
        label_window = 3600  # 1hr window
        window_start = failure_ts - label_window
        window_end   = failure_ts
    else:
        label = None
        confidence = 0.0
        failure_ts = None
        now = max([r.timestamp for r in telem.resource_records]+[0])
        window_start = now - 3600
        window_end   = now
    # Format resource/journal series
    metrics = set(r.metric_type for r in telem.resource_records)
    resource_series = {m: [r.value for r in telem.resource_records if r.metric_type==m] for m in metrics}
    journal_series = [
        {
            "offset_seconds": int(j.timestamp - window_start),
            "level": j.level,
            "unit": j.unit,
            "message": j.message,
        }
        for j in telem.journal_records if window_start <= j.timestamp <= window_end
    ]
    return LabeledEvent(
        entity_id=telem.entity_id,
        failure_class=label,
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

def run_labelling(entity_telemetries: List[EntityTelemetry], hierarchies, poolings, output_dir="data/labeled"):
    os.makedirs(output_dir, exist_ok=True)
    for telem in entity_telemetries:
        if not telem.has_both_streams:
            continue
        hierarchy = hierarchies.get(telem.entity_id, {})
        pool_context = poolings.get(telem.entity_id, {})
        labeled = label_entity(telem, hierarchy, pool_context)
        with open(f"{output_dir}/{telem.entity_id}.jsonl", "w") as f:
            f.write(json.dumps(labeled.__dict__)+"\n")