from ingestion.aggregator import poll_connectors
import time
import yaml
import asyncio

def test_aggregator_both_streams():
    with open("config/connectors.yaml") as f:
        conf = yaml.safe_load(f)
    now = time.time()
    t0 = now - 600
    telemetry = asyncio.run(poll_connectors(conf["connectors"], t0, now))
    for t in telemetry:
        assert isinstance(t.resource_records, list)
        assert isinstance(t.journal_records, list)
    # At least one entity should have both streams
    assert any(t.has_both_streams for t in telemetry)

test_aggregator_both_streams()