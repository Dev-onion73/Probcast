import json
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from statistics import mean

# Assume imports from ingestion.schema and hierarchy.encoder
from ingestion.ingest_and_normalize import ingest_entities
from hierarchy.encoder import build_hierarchy

console = Console()

def show_entity_summary(telemetry):
    rr = telemetry.resource_records
    jr = telemetry.journal_records
    meta = telemetry.metadata
    metrics_by_type = {}
    for m in rr:
        metrics_by_type.setdefault(m.metric_type, []).append(m.value)
    jr_by_level = Counter([j.level for j in jr])

    console.rule(f"L0 — Entity: {telemetry.entity_id}")
    print("Path: ", f"{meta.org}/{meta.environment}/{meta.subnet}/{meta.host}")
    print(f"Both streams:     {'✓' if rr and jr else '✗'}")
    print(f"Resource records: {len(rr)}")
    print(f"Journal records:  {len(jr)}\n")

    # Resource summary
    print("Resource summary:")
    for mt, vals in metrics_by_type.items():
        print(f"  {mt:14} min={min(vals):.3f}  mean={mean(vals):.3f}  max={max(vals):.3f}")
    print()

    # Journal summary
    print("Journal severity:")
    for lvl in ["INFO", "WARNING", "ERROR", "CRITICAL"]:
        print(f"  {lvl:<8}: {jr_by_level.get(lvl,0)}")
    print()

    # Failure anchors
    anchors = [j for j in jr if j.tags and j.tags.get("is_anchor")]
    print(f"Failure anchors: {len(anchors)}")
    for a in anchors:
        ts = int(a.timestamp)
        print(f"  [{a.level}] {a.unit}: {a.message} (t={ts})")
    print()

def pretty_hierarchy_tree(hnode, parent_tree=None):
    name = f"{hnode.name}"
    if hnode.level == "subnet":
        name += f" [n={len(hnode.children)}]"
    t = Tree(f"{hnode.level}: {name}") if parent_tree is None else parent_tree.add(f"{hnode.level}: {name}")
    for c in hnode.children:
        pretty_hierarchy_tree(c, t)
    return t

def main():
    # Gather entities
    entities = list(ingest_entities(window_minutes=120))
    # L0: For each entity, show summary
    for t in entities:
        show_entity_summary(t)

    # L1: Build and pretty-print hierarchy
    hierarchy = build_hierarchy(entities)
    console.rule("L1 — Hierarchy Graph")
    tree = pretty_hierarchy_tree(hierarchy)
    console.print(tree)

    # Optionally, print a compact aggregation matrix or PoolingStructure per entity (not shown here)

if __name__ == "__main__":
    main()