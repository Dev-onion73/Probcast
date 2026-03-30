import yaml
import numpy as np

CONNECTOR_CONFIG = "config/connectors.yaml"

def load_entities_from_config(config_path=CONNECTOR_CONFIG):
    """Load entities (host, subnet, env, org) from config."""
    with open(config_path, "r") as f:
        conf = yaml.safe_load(f)
    entities = []
    for conn in conf["connectors"]:
        for e in conn["entities"]:
            m = e.get("metadata", {})
            entity = {
                "host":        m.get("host", e.get("id")),
                "subnet":      m.get("subnet", "UNKNOWN"),
                "environment": m.get("environment", "UNKNOWN"),
                "org":         m.get("org", "UNKNOWN"),
            }
            entities.append(entity)
    return entities

def build_hierarchy(entities):
    """Create nested hierarchy dict org→env→subnet→host."""
    hierarchy = {"org": {}}
    for e in entities:
        o = e["org"]
        env = e["environment"]
        subnet = e["subnet"]
        host = e["host"]
        hierarchy["org"].setdefault(o, {})
        hierarchy["org"][o].setdefault(env, {})
        hierarchy["org"][o][env].setdefault(subnet, [])
        if host not in hierarchy["org"][o][env][subnet]:
            hierarchy["org"][o][env][subnet].append(host)
    return hierarchy

def build_aggregation_matrix(hierarchy, entities):
    org = next(iter(hierarchy["org"]))
    envs = hierarchy["org"][org]
    subnets = []
    hosts = [e["host"] for e in entities]
    for env_name, subnet_map in envs.items():
        for subnet in subnet_map:
            if subnet not in subnets:
                subnets.append(subnet)
    S = np.zeros((len(subnets), len(hosts)), dtype=int)
    for s_idx, subnet in enumerate(subnets):
        for h_idx, h in enumerate(hosts):
            for env_name, subnet_map in envs.items():
                if subnet in subnet_map and h in subnet_map[subnet]:
                    S[s_idx, h_idx] = 1
    return S, subnets, hosts

def get_hierarchy_model_inputs(config_path=CONNECTOR_CONFIG):
    """
    Returns: hierarchy, S (matrix), hosts, subnets
    """
    entities = load_entities_from_config(config_path)
    hierarchy = build_hierarchy(entities)
    S, subnets, hosts = build_aggregation_matrix(hierarchy, entities)
    return hierarchy, S, hosts, subnets

# CLI usage: pretty tree print, aggregation matrix print for quick test
def pretty_hierarchy_tree(hierarchy):
    lines = []
    for org, envs in hierarchy["org"].items():
        lines.append("org: " + org)
        for env, subnets in envs.items():
            lines.append(f"  env: {env}")
            for subnet, hosts in subnets.items():
                lines.append(f"    subnet: {subnet}")
                for host in hosts:
                    lines.append(f"      host: {host}")
    return lines

def print_box(title):
    width = len(title) + 6
    print("┌" + "─" * (width - 2) + "┐")
    print(f"│  {title}  │")
    print("└" + "─" * (width - 2) + "┘")

def print_hierarchy_tree(lines):
    print_box("Hierarchy Tree")
    for line in lines:
        print(line)
    print()

def print_aggregation_matrix(S, subnets, hosts):
    print_box("Aggregation Matrix (rows = subnets, columns = hosts)")
    pad = max(max(len(h) for h in hosts), 8) + 2
    row_hdr = max([len(s) for s in subnets] + [10]) + 2
    col_labels = "".join(h.rjust(pad) for h in hosts)
    print(" " * row_hdr + col_labels)
    print("-" * (row_hdr + pad * len(hosts)))
    for i, subnet in enumerate(subnets):
        row = subnet.ljust(row_hdr)
        for j in range(len(hosts)):
            val = "✓" if S[i, j] else "·"
            row += val.center(pad)
        print(row)
    print()

if __name__ == "__main__":
    print("=== L1 HIERARCHY ENCODER/MATRIX TEST (from config) ===\n")
    hierarchy, S, hosts, subnets = get_hierarchy_model_inputs()
    print(f"Loaded {len(hosts)} entities.\n")
    h_lines = pretty_hierarchy_tree(hierarchy)
    print_hierarchy_tree(h_lines)
    print_aggregation_matrix(S, subnets, hosts)
    print("✓ L1 test succeeded (entities and topology from config).")