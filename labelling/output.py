from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class LabeledEvent:
    entity_id:         str
    failure_class:     Optional[str]
    failure_timestamp: Optional[float]
    window_start:      float
    window_end:        float
    hierarchy:         dict
    pool_context:      dict
    resource_series:   Dict[str, List[float]]
    journal_series:    List[dict]
    label:             Optional[str]
    confidence:        float