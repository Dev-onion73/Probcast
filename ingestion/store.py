from typing import Dict
from ingestion.schema import EntityTelemetry

class InMemoryStore:
    def __init__(self):
        self.entities: Dict[str, EntityTelemetry] = {}

    def add(self, telemetry: EntityTelemetry):
        self.entities[telemetry.entity_id] = telemetry

    def all(self):
        return list(self.entities.values())