import asyncio
import httpx
import yaml
import time
from ingestion.normalizer import normalize_prometheus_records, normalize_journal_records
from ingestion.schema import EntityTelemetry, EntityMeta

async def check_availability(connector_url: str):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{connector_url}/health", timeout=3.0)
            return resp.status_code == 200
    except Exception:
        return False

async def poll_connectors(connectors_conf, start_ts, end_ts):
    # Aggregate by entity_id: {"entity_id": {"resource": [...], "journal": [...], "meta": meta}}
    entity_streams = {}
    async with httpx.AsyncClient() as client:
        for cdata in connectors_conf:
            url = cdata["url"]
            src = cdata["source_type"]
            avail = await check_availability(url)
            if not avail:
                print(f"[Aggregator] Connector {url} unavailable")
                continue
            for entity in cdata["entities"]:
                eid = entity["id"]
                resp = await client.get(
                    f"{url}/data",
                    params={"entity_id": eid, "start_ts": start_ts, "end_ts": end_ts},
                    timeout=5.0
                )
                if resp.status_code != 200:
                    print(f"[Aggregator] {src} {eid}: failed to GET data")
                    continue
                records = resp.json()
                if src == "prometheus":
                    normed = normalize_prometheus_records(records)
                    entity_streams.setdefault(eid, {"resource": [], "journal": [], "meta": entity["metadata"]})
                    entity_streams[eid]["resource"].extend(normed)
                elif src == "journal":
                    normed = normalize_journal_records(records)
                    entity_streams.setdefault(eid, {"resource": [], "journal": [], "meta": entity["metadata"]})
                    entity_streams[eid]["journal"].extend(normed)
                # Add more 'elif' as you implement CloudWatch, SIEM, etc.

    all_telemetry = []
    for eid, streams in entity_streams.items():
        telem = EntityTelemetry(
            entity_id=eid,
            metadata=EntityMeta(**streams["meta"]),
            resource_records=streams["resource"],
            journal_records=streams["journal"]
        )
        all_telemetry.append(telem)
    return all_telemetry

if __name__ == "__main__":
    with open("config/connectors.yaml") as f:
        conf = yaml.safe_load(f)
    now = time.time()
    t0 = now - 10000  # last 10 minutes
    connector_cfgs = conf["connectors"]
    telemetry = asyncio.run(poll_connectors(connector_cfgs, t0, now))
    for t in telemetry:
        print(f"[Aggregator] Entity {t.entity_id} — Resource: {len(t.resource_records)} records, "
              f"Journal: {len(t.journal_records)} records, Both: {'✓' if t.has_both_streams else '✗'}")
    # Optionally print a few sample records for inspection
    for t in telemetry:
        if t.has_both_streams:
            print(f"\nSample for {t.entity_id}:")
            print("  Resource:", t.resource_records[0] if t.resource_records else "N/A")
            print("  Journal :", t.journal_records[0] if t.journal_records else "N/A")