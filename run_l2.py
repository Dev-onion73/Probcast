import yaml, time, asyncio
from ingestion.aggregator import poll_connectors
from hierarchy.encoder import infer_hierarchy
from hierarchy.pooling import partial_pooling_weights
from labelling.pipeline import run_labelling

# 1. Poll for telemetry
with open("config/connectors.yaml") as f:
    conf = yaml.safe_load(f)
now = time.time()
t0 = now - 3600  # 1 hour window
entities = asyncio.run(poll_connectors(conf["connectors"], t0, now))

# 2. Hierarchy/pooling
tree = infer_hierarchy(entities)
group_membership = {}
for env, env_subnets in tree["org"]["environments"].items():
    for subnet, hosts in env_subnets.items():
        group_membership[subnet] = hosts
poolings = {eid: {"pooling_weight": 0.5} for members in group_membership.values() for eid in members}  # demo value
hierarchies = {e.entity_id: {
    "host": e.metadata.host,
    "subnet": e.metadata.subnet,
    "environment": e.metadata.environment,
    "org": e.metadata.org
} for e in entities}

# 3. Run labelling
run_labelling(entities, hierarchies, poolings)