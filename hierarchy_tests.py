import yaml
import time
import asyncio
import pprint
import numpy as np

from ingestion.aggregator import poll_connectors
from hierarchy.encoder import infer_hierarchy
from hierarchy.matrix import build_aggregation_matrix,print_aggregation_matrix
from hierarchy.pooling import partial_pooling_weights

def test_l1_hierarchy_and_pooling():
    # Step 1: Load connectors configuration and run aggregator
    with open("config/connectors.yaml") as f:
        conf = yaml.safe_load(f)
    now = time.time()
    t0 = now - 900
    connector_cfgs = conf["connectors"]

    # Gather EntityTelemetry objects
    entities = asyncio.run(poll_connectors(connector_cfgs, t0, now))

    # Step 2: Infer hierarchy tree
    tree = infer_hierarchy(entities)
    print("\n━━ Hierarchy tree ━━")
    pprint.pprint(tree)
    assert "org" in tree, "Hierarchy tree missing 'org' level"
    assert "environments" in tree["org"], "Hierarchy tree missing 'environments'"

    # Step 3: Extract group membership (by subnet)
    group_membership = {}
    for env, subnets_obj in tree["org"]["environments"].items():
        for subnet, hosts in subnets_obj.items():
            group_membership[subnet] = hosts
    print("\n━━ Group membership by subnet ━━")
    pprint.pprint(group_membership)
    assert group_membership, "No groups detected; check hierarchy and entity metadata"

    # Step 4: Compute partial pooling weights
    pooling_stats = partial_pooling_weights(entities, group_membership)
    print("\n━━ Pooling weights/statistics ━━")
    for (group, eid), vals in pooling_stats.items():
        print(f"{group}:{eid} pooling_weight={vals['pooling_weight']:.2f}, "
              f"group_mean={vals['group_mean']:.3f}, group_var={vals['group_var']:.4f}")
        # Pooling weight should be in [0, 1]
        assert 0.0 <= vals['pooling_weight'] <= 1.0
        assert eid in group_membership[group]

    # Step 5: Build aggregation matrix S
    matrix, entity_ids, subnets = build_aggregation_matrix(tree)
    # Example:
# matrix, entity_ids, subnets = build_aggregation_matrix(tree)
    print_aggregation_matrix(matrix, entity_ids, subnets)
    print("\nAll hierarchy L1 tests passed!")

if __name__ == "__main__":
    test_l1_hierarchy_and_pooling()