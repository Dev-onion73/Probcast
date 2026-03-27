# Canonical → actual CSV column mapping for etcd-minikube and kalic entities
ENTITY_VARIANTS = {
    "etcd-minikube": {
        "cpu_usage": "CPU-etcd-minikube",
        "memory_usage": "Memory-etcd-minikube",
        "memory_cache": "Memory_Cache-etcd-minikube",
        "disk_io_write": "write-etcd-minikube"
    },
    "kalic": {
        "cpu_usage": "CPU-kalic",
        "memory_usage": "Memory-kalic",
        "memory_cache": "Memory_Cache-kalic",
        "disk_io_write": "write-kalic"
    }
}

# List of canonical features to generate
DEFAULT_METRICS = ["cpu_usage", "memory_usage", "memory_cache", "disk_io_write"]

# Probability distribution for classes (can adjust as needed)
FAILURE_CLASS_PROBS = {
    "cpu_overload": 0.17,
    "memory_exhaustion": 0.17,
    "storage_failure": 0.17,
    "network_downtime": 0.17,
    "service_crash": 0.16,
    "dependency_timeout": 0.16,
    None: 0.20
}

# Entity template hierarchy
ENTITY_TEMPLATE = {
    "host":        "simulated-entity",
    "subnet":      "sim-subnet",
    "environment": "production",
    "org":         "acme-corp"
}