from ingestion.schema import EntityTelemetry, EntityMeta
from typing import List, Dict

def infer_hierarchy(entities: List[EntityTelemetry]) -> Dict:
    # Step 1 Extract prefix tokens and group by common tokens (simple logic)
    groups = {}
    for entity in entities:
        toks = entity.entity_id.split("-")
        group_key = "-".join(toks[:-1]) if len(toks) > 1 else entity.entity_id
        groups.setdefault(group_key, []).append(entity)

    # Step 2 Build hierarchy dict
    hierarchy = {}
    for group, members in groups.items():
        hierarchy[group] = [e.entity_id for e in members]

    # Step 3 Assign org/environment/subnet/host for each
    tree = {"org": {"name": "demo", "environments": {}}}
    for entity in entities:
        env = entity.metadata.environment
        subnet = entity.metadata.subnet
        tree["org"]["environments"].setdefault(env, {}).setdefault(subnet, []).append(entity.entity_id)
    return tree