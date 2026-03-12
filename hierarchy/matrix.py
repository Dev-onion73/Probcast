import numpy as np
from typing import List, Dict

def build_aggregation_matrix(hierarchy_tree: Dict) -> np.ndarray:
    # Simple: leaves = all entity_ids, rows = groupings
    # For demo: one subnet level only
    subnets = []
    entity_ids = set()
    for env in hierarchy_tree["org"]["environments"].values():
        for subnet, hosts in env.items():
            subnets.append(subnet)
            for eid in hosts:
                entity_ids.add(eid)
    entity_ids = sorted(entity_ids)
    matrix = np.zeros((len(subnets), len(entity_ids)), dtype=int)
    for i, env in enumerate(hierarchy_tree["org"]["environments"].values()):
        for j, (subnet, hosts) in enumerate(env.items()):
            for eid in hosts:
                k = entity_ids.index(eid)
                matrix[j,k] = 1
    return matrix, entity_ids, subnets


def print_aggregation_matrix(matrix: np.ndarray, entity_ids: list, subnets: list):
    # Compute column widths for nice alignment
    col_width = max([len(eid) for eid in entity_ids] + [8]) + 2
    row_label_width = max([len(sub) for sub in subnets] + [12]) + 2

    # Header
    header = " " * row_label_width + "".join([eid.rjust(col_width) for eid in entity_ids])
    print(header)
    print("-" * len(header))

    # Rows
    for row_idx, subnet in enumerate(subnets):
        row = subnet.ljust(row_label_width)
        row += "".join([str(int(val)).rjust(col_width) for val in matrix[row_idx]])
        print(row)