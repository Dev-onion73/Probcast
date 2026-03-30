import time
import yaml
import requests

CONNECTOR_CONFIG = "config/connectors.yaml"
REGIME_CONFIG = "config/regimes.yaml"
SERVER_URL = "http://localhost:8101"

FAILURE_CLASSES = [
    "cpu_overload",
    "memory_exhaustion",
    "storage_failure",
    "network_downtime",
    "service_crash",
    "dependency_timeout",
]

def load_anchor_messages(regime_config=REGIME_CONFIG):
    """Load mapping of failure classes to anchor phrases."""
    try:
        with open(regime_config) as f:
            data = yaml.safe_load(f)
        # Check for anchor messages in YAML
        if "anchors" in data:
            return {c: data["anchors"].get(c, "") for c in FAILURE_CLASSES}
    except Exception:
        pass
    # Fallbacks (minimal, hardcoded)
    return {
        "cpu_overload":         "CPU overload: run queue length exceeds core count",
        "memory_exhaustion":    "Memory exhaustion: no free pages available",
        "storage_failure":      "Storage failure: device sda unresponsive",
        "network_downtime":     "Network downtime: interface eth0 down",
        "service_crash":        "Service app.service: Service crashed",
        "dependency_timeout":   "Dependency timeout: db.service failed within SLA",
    }

def load_entities(config_path=CONNECTOR_CONFIG):
    """Get entity IDs from connector config."""
    with open(config_path) as f:
        conf = yaml.safe_load(f)
    return [e["id"] for c in conf["connectors"] for e in c.get("entities", [])]

def probe_failure_labels(entity_ids, server_url, anchor_phrases, window_seconds=600):
    """
    For each entity, probes logs for presence of anchor phrases marking a failure event.
    Returns: found_per_entity (eid→set of detected classes), found_by_class (class→list of logs).
    """
    now = int(time.time())
    start_ts = now - window_seconds
    found_per_entity = {}
    found_by_class = {cls: [] for cls in FAILURE_CLASSES}
    for eid in entity_ids:
        try:
            resp = requests.get(
                f"{server_url}/journal/data",
                params={"entity_id": eid, "start_ts": start_ts, "end_ts": now},
                timeout=10,
            )
            logs = resp.json()
        except Exception:
            logs = []
        found = set()
        for log in logs:
            for cls, phrase in anchor_phrases.items():
                if (
                    phrase in log.get("message", "")
                    and log.get("level", "") == "CRITICAL"
                    and log.get("tags", {}).get("is_anchor")
                ):
                    found.add(cls)
                    found_by_class[cls].append({"entity": eid, "log": log})
        found_per_entity[eid] = found
    return found_per_entity, found_by_class

if __name__ == "__main__":
    entities = load_entities()
    anchor_phrases = load_anchor_messages()
    print(f"\nProbing {len(entities)} entities for coverage of: {', '.join(FAILURE_CLASSES)} ?")
    print("Waiting for all failure class anchors to be detected in any entity stream...\n")
    window = 600  # 10 minutes

    while True:
        found_per_entity, found_by_class = probe_failure_labels(
            entities, SERVER_URL, anchor_phrases, window_seconds=window
        )

        print("\nOccurrence by entity:")
        for eid, found in found_per_entity.items():
            print(f"  {eid:22}: {' '.join(sorted(found)) if found else '---'}")
        print("\nCoverage summary:")
        for cls in FAILURE_CLASSES:
            status = "✓" if found_by_class[cls] else "MISSING"
            print(f"  {cls:20}: {status}")

        missing = [cls for cls, founds in found_by_class.items() if not founds]
        if not missing:
            print("\nSUCCESS: ALL FAILURE ANCHORS FOUND!")
            for cls in FAILURE_CLASSES:
                print(f"\nSample for {cls}: Entity={found_by_class[cls][0]['entity']}")
                print(found_by_class[cls][0]['log'])
            break
        print("Still missing: " + ", ".join(missing))
        time.sleep(5)