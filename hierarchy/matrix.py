import numpy as np
from typing import Dict, List, Tuple

def build_aggregation_matrix(hierarchy_graph) -> Tuple[np.ndarray, List[str], List[str]]:
    """
    Accepts a HierarchyGraph with .as_tree(). Returns (S, entity_ids, subnets)
    """
    htree = hierarchy_graph.as_tree()
    subnets = []
    entity_ids = []
    envs = htree.get("org", {}).get("environments", {})
    for env_name, subnet_map in envs.items():
        for subnet, hosts in subnet_map.items():
            if subnet not in subnets:
                subnets.append(subnet)
            for eid in hosts:
                if eid not in entity_ids:
                    entity_ids.append(eid)
    matrix = np.zeros((len(subnets), len(entity_ids)), dtype=int)
    for s_idx, subnet in enumerate(subnets):
        for env_name, subnet_map in envs.items():
            hosts = subnet_map.get(subnet, [])
            for h in hosts:
                col_idx = entity_ids.index(h)
                matrix[s_idx, col_idx] = 1
    return matrix, entity_ids, subnets

def print_aggregation_matrix(matrix: np.ndarray, entity_ids: List[str], subnets: List[str]):
    pad = max([len(eid) for eid in entity_ids] + [12]) + 2
    row_hdr = max([len(s) for s in subnets] + [12]) + 2
    header = " " * row_hdr + "".join([eid.rjust(pad) for eid in entity_ids])
    print(header)
    print('-' * len(header))
    for row_idx, subnet in enumerate(subnets):
        row = subnet.ljust(row_hdr) + "".join([str(int(val)).rjust(pad) for val in matrix[row_idx]])
        print(row)