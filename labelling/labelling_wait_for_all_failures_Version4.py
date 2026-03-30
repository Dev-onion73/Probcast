import os
import time
import json
from collections import defaultdict

LABELED_EVENTS_PATH = "data/labeled/l2_labeled_events.jsonl"
L2_PIPELINE = "labelling/pipeline.py"
FAILURE_CLASSES = [
    "cpu_overload",
    "memory_exhaustion",
    "storage_failure",
    "network_downtime",
    "service_crash",
    "dependency_timeout",
]

def run_l2_pipeline():
    # Run labelling pipeline (system call)
    ret = os.system(f"python {L2_PIPELINE}")
    if ret != 0:
        print(f"WARNING: {L2_PIPELINE} exited with nonzero code ({ret})")

def parse_labeled_events():
    found = defaultdict(list)
    if not os.path.exists(LABELED_EVENTS_PATH):
        return found
    with open(LABELED_EVENTS_PATH) as f:
        for line in f:
            evt = json.loads(line)
            event_class = evt.get("failure_class")
            if event_class and event_class in FAILURE_CLASSES:
                found[event_class].append(evt)
    return found

def all_classes_found(found: dict) -> bool:
    return all(c in found and len(found[c]) > 0 for c in FAILURE_CLASSES)

def print_summary(found: dict):
    print("\nDetected failure classes so far:")
    for c in FAILURE_CLASSES:
        count = len(found.get(c, []))
        print(f"  {c:22}: {count}")
    missing = [c for c in FAILURE_CLASSES if c not in found or not found[c]]
    if missing:
        print(f"\nStill missing: {', '.join(missing)}")
    else:
        print("\nAll failure classes detected at least once!")

def main(sleep_sec=12):
    print("Starting L2 labelling fetch loop...")
    tries = 0
    found = {}
    while True:
        tries += 1
        print(f"\nIteration {tries}: Running labelling pipeline and checking output...")
        run_l2_pipeline()
        found = parse_labeled_events()
        print_summary(found)
        if all_classes_found(found):
            print("\nSUCCESS: Detected at least one labeled event for all failure classes!")
            break
        time.sleep(sleep_sec)

    # Optionally print first found example for each:
    print("\n--- Example labeled event per class ---")
    for c in FAILURE_CLASSES:
        example = found[c][0]
        print(f"\nClass: {c}")
        print(json.dumps(example, indent=2))

if __name__ == "__main__":
    main()