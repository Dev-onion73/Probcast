import asyncio
import httpx
import yaml
import time
from ingestion.normalizer import normalize_prometheus_records, normalize_journal_records
from ingestion.schema import EntityTelemetry, EntityMeta

def load_connector_config(path="config/connectors.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)

async def poll_connectors(connectors_conf, start_ts, end_ts):
    entity_streams = {}
    async with httpx.AsyncClient() as client:
        for conn in connectors_conf:
            url = conn["url"]
            src = conn["source_type"]
            try:
                resp = await client.get(f"{url}/health", timeout=3.0)
                if resp.status_code != 200:
                    print(f"[Aggregator] Connector {url} unavailable")
                    continue
            except Exception:
                print(f"[Aggregator] Connector {url} unavailable")
                continue
            for entity in conn["entities"]:
                eid = entity["id"]
                try:
                    resp = await client.get(
                        f"{url}/data",
                        params={"entity_id": eid, "start_ts": start_ts, "end_ts": end_ts},
                        timeout=5.0
                    )
                    if resp.status_code != 200:
                        print(f"[Aggregator] {src} {eid}: failed to GET data")
                        continue
                    records = resp.json()
                    entity_streams.setdefault(eid, {"resource": [], "journal": [], "meta": entity["metadata"]})
                    if src in ("prometheus", "cloudwatch"):
                        entity_streams[eid]["resource"].extend(normalize_prometheus_records(records))
                    elif src in ("journal", "siem"):
                        entity_streams[eid]["journal"].extend(normalize_journal_records(records))
                except Exception as ex:
                    print(f"[Aggregator] {src} {eid}: exception {ex}")
    all_telemetry = []
    for eid, streams in entity_streams.items():
        telem = EntityTelemetry(
            entity_id        = eid,
            metadata         = EntityMeta(**streams["meta"]),
            resource_records = streams["resource"],
            journal_records  = streams["journal"],
        )
        all_telemetry.append(telem)
    return all_telemetry

def run_and_get_telemetry(past_seconds=3600):
    conf = load_connector_config()
    now = time.time()
    t0 = now - past_seconds
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        poll_connectors(conf["connectors"], t0, now)
    )