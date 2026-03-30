from typing import List, Dict
import numpy as np
from ingestion.schema import EntityTelemetry

def partial_pooling_weights(entities: List[EntityTelemetry], group_membership: Dict[str, List[str]]) -> Dict:
    """
    Returns a dict, keyed by (group, entity_id), with pooling stats:
      {
        (group_id, entity_id): {
            "pooling_weight": w,
            "group_mean": float,
            "group_var": float,
        }
      }
    """
    group_stats = {}
    for group, members in group_membership.items():
        vals = []
        for ent in entities:
            if ent.entity_id in members:
                cpu = [r.value for r in ent.resource_records if str(r.metric_type)=="cpu_usage"]
                if cpu:
                    vals.append(np.mean(cpu))
        group_mean = np.mean(vals) if vals else 0
        group_var = np.var(vals) if vals else 1
        for ent in entities:
            if ent.entity_id in members:
                ent_cpu = [r.value for r in ent.resource_records if str(r.metric_type)=="cpu_usage"]
                indiv_var = np.var(ent_cpu) if ent_cpu else 1
                w = group_var / (group_var + indiv_var) if (group_var + indiv_var) != 0 else 0.5
                group_stats[(group, ent.entity_id)] = {
                    "pooling_weight": w,
                    "group_mean": group_mean,
                    "group_var": group_var
                }
    return group_stats