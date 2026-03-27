import random

FAILURE_ANCHORS = {
    "cpu_overload": [
        {"offset_seconds": -1800, "level": "WARNING", "unit": "kernel", "message": "CPU soft lockup detected on CPU#N"},
        {"offset_seconds": -900, "level": "ERROR", "unit": "kernel", "message": "watchdog: BUG: soft lockup - CPU#N stuck for 22s"},
        {"offset_seconds": 0, "level": "CRITICAL", "unit": "kernel", "message": "CPU overload: run queue length exceeds core count"}
    ],
    "memory_exhaustion": [
        {"offset_seconds": -2400, "level": "WARNING", "unit": "kernel", "message": "kswapd0: page allocation stalls"},
        {"offset_seconds": -900, "level": "ERROR", "unit": "kernel", "message": "Out of memory: kill process N score N"},
        {"offset_seconds": 0, "level": "CRITICAL", "unit": "kernel", "message": "Memory exhaustion: no free pages available"}
    ],
    "storage_failure": [
        {"offset_seconds": -3600, "level": "WARNING", "unit": "kernel", "message": "EXT4-fs error (sda1): ext4_find_entry:1455"},
        {"offset_seconds": -1200, "level": "ERROR", "unit": "kernel", "message": "sd 2:0:0:0: [sda] FAILED Result: hostbyte=DID_OK"},
        {"offset_seconds": 0, "level": "CRITICAL", "unit": "kernel", "message": "Storage failure: device sda unresponsive"}
    ],
    "network_downtime": [
        {"offset_seconds": -1800, "level": "WARNING", "unit": "NetworkManager", "message": "device eth0: link speed below threshold"},
        {"offset_seconds": -900, "level": "ERROR", "unit": "NetworkManager", "message": "device eth0: carrier lost"},
        {"offset_seconds": 0, "level": "CRITICAL", "unit": "NetworkManager", "message": "Network downtime: interface eth0 down"}
    ],
    "service_crash": [
        {"offset_seconds": -600, "level": "ERROR", "unit": "app.service", "message": "Unhandled exception in request handler"},
        {"offset_seconds": -60, "level": "CRITICAL", "unit": "systemd", "message": "Service app.service: main process exited code=killed"},
        {"offset_seconds": 0, "level": "CRITICAL", "unit": "systemd", "message": "Service app.service: Service crashed"}
    ],
    "dependency_timeout": [
        {"offset_seconds": -1800, "level": "WARNING", "unit": "app.service", "message": "Downstream call to db.service exceeded Nms"},
        {"offset_seconds": -120, "level": "ERROR", "unit": "app.service", "message": "All retries exhausted for db.service"},
        {"offset_seconds": 0, "level": "CRITICAL", "unit": "app.service", "message": "Dependency timeout: db.service failed within SLA"}
    ]
}

def make_journal_series(failure_class, window_start, window_end, normal_rate=0.005):
    events = []
    if failure_class:
        for evt in FAILURE_ANCHORS[failure_class]:
            t = window_end + evt["offset_seconds"]
            if window_start <= t <= window_end:
                event = evt.copy()
                event["timestamp"] = t
                events.append(event)
    # Add a few benign noise logs
    for _ in range(random.randint(0, 2)):
        evt = {
            "offset_seconds": random.randint(-1800, -60),
            "level": "INFO",
            "unit": "sshd",
            "message": "Accepted publickey for user from 10.x.x.x",
            "timestamp": window_start + random.randint(0, max(1, window_end - window_start - 1))
        }
        if window_start <= evt["timestamp"] < window_end:
            events.append(evt)
    events.sort(key=lambda e: e["timestamp"])
    # Offset relative to window_start for model input consistency
    for e in events:
        e["offset_seconds"] = e["timestamp"] - window_start
        del e["timestamp"]
    return events