import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import box

# Configurable paths
PRED_PATH = Path("outputs/latest_preds.json")
LABEL_PATH = Path("outputs/latest_labels.json")

def load_jsonl_or_json(p):
    if not Path(p).exists():
        return []
    with open(p) as f:
        try:
            data = json.load(f)
            # if file is a JSON lines file instead
            if isinstance(data, list):
                return data
            else:
                return [data]
        except Exception:
            f.seek(0)
            return [json.loads(ln) for ln in f if ln.strip()]

def print_preds_table(preds, filter_entity=None, filter_horizon=None):
    if not preds:
        print("[TUI] No prediction data found.")
        return
    # all class names
    all_classes = list(next(iter(preds))["probs_per_class"].keys())
    all_horizons = sorted({row.get('forecast_horizon', '') for row in preds})
    table = Table(show_lines=True, box=box.SIMPLE)
    table.add_column("Entity", style="bold")
    table.add_column("Horizon", justify="right")
    for c in all_classes:
        table.add_column(f"{c}", justify="right")
    for row in preds:
        eid = row["entity_id"]
        horizon = row.get("forecast_horizon", str(row.get("delta_t_seconds", "")))
        if filter_entity and eid != filter_entity:
            continue
        if filter_horizon and horizon != filter_horizon:
            continue
        ppc = row["probs_per_class"]
        table.add_row(
            eid,
            horizon,
            *[f"{float(ppc[c]):.3f}" for c in all_classes]
        )
    console = Console()
    console.print(table)

def print_labels_table(labels):
    if not labels:
        print("[TUI] No label data found.")
        return
    table = Table(box=box.SIMPLE)
    table.add_column("Entity", style="bold")
    table.add_column("Detected Labels")
    for row in labels:
        table.add_row(row.get("entity_id", "?"), ", ".join(row.get("detected_labels", [])))
    console = Console()
    console.print(table)

def main():
    preds = load_jsonl_or_json(PRED_PATH)
    labels = load_jsonl_or_json(LABEL_PATH)
    print("\n== ProbCast TUI Results Viewer ==")
    if preds:
        print("\n[MODEL PREDICTIONS]:")
        print_preds_table(preds)
    if labels:
        print("\n[LABELS]:")
        print_labels_table(labels)
    # Basic filter prompt for user
    try:
        while True:
            choice = input("\nFilter by entity id (enter to skip): ").strip()
            if choice:
                print_preds_table(preds, filter_entity=choice)
            else:
                break
        while True:
            choice = input("Filter by forecast horizon (e.g. '90d', enter to skip): ").strip()
            if choice:
                print_preds_table(preds, filter_horizon=choice)
            else:
                break
    except KeyboardInterrupt:
        print("\n[TUI] Exiting.")

if __name__ == "__main__":
    main()