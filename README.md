# ProbCast Demo: End-to-End L0–L3 Failure Forecasting Pipeline

**ProbCast** is a unified pipeline for hierarchical probabilistic risk forecasting in infrastructure telemetry, supporting multi-source ingestion, dynamic entity hierarchy, weak-supervision labeling, and model-ready event construction.

This demonstration guide summarizes how to run the full L0-L3 pipeline—from live telemetry connector ingestion through automatic labeling and model training, to runtime probabilistic inference—on your system. *Synthetic dataset generation is not covered here (see L3 and appendix in the implementation docs for that track).*

---

## Table of Contents

1. [Pipeline Overview](#pipeline-overview)
2. [Prerequisites](#prerequisites)
3. [Project Structure](#project-structure)
4. [Step 1: Start the Connector Servers](#step-1-start-the-connector-servers)
5. [Step 2: Run the Pipeline (L0–L3)](#step-2-run-the-pipeline-l0-l3)
6. [Step 3: Model Training and Inference](#step-3-model-training-and-inference)
7. [Step 4: Real-Time Dashboard (Optional)](#step-4-real-time-dashboard-optional)
8. [Expected Outputs](#expected-outputs)
9. [Troubleshooting](#troubleshooting)
10. [References](#references)

---

## Pipeline Overview

The ProbCast demonstration consists of:

- **L0: Ingestion & normalization** – Pulls resource and log data from independent, live FastAPI servers (mocked Prometheus, journald, etc.), normalizing into a unified record format.
- **L1: Hierarchy encoding** – Dynamically infers the topology (host, subnet, environment, org) and constructs the aggregation matrix for probabilistic pooling and attribution.
- **L2: Labelling pipeline** – Applies Drain3 mining on logs, then programmatic labeling rules to generate model-ready "LabeledEvent" windows for all entities.
- **L3: Model-ready event feed** – Labeled, featureized, and context-enriched event JSONL files, immediately consumable by the probabilistic model for training and inference.

> The demonstration shows full, live construction from streaming telemetry to labeled data and into the model,
> with no manual step or dataset editing required.

---

## Prerequisites

- **Python 3.10+**
- **Linux or macOS recommended** (Windows possible, but journald mock uses Unix-style paths)
- **All dependencies pinned in `requirements.txt`**

### Initial setup

```bash
git clone https://github.com/Dev-onion73/Probcast.git
cd Probcast
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Edit as needed for custom ports/entities
```

---

## Project Structure

- `config/connectors.yaml` – registry of all telemetry connectors/entities
- `connectors/` – independent FastAPI servers (Prometheus, journald, CloudWatch, SIEM, etc)
- `ingestion/` – polling, normalization, storage of synchronized streams per entity
- `hierarchy/` – dynamic inference and aggregation matrix logic
- `labelling/` – Drain3 mining, labeling functions, labeling pipeline
- `models/` – model code for probabilistic (Pyro) learning and inference
- `data/labeled/` – output: labeled event windows, per entity, as JSONL

---

## Step 1: Start the Connector Servers

setup .env file as follows

```bash
MOCK_PROMETHEUS_PORT=8001
POLL_INTERVAL=60
```

_Open a new terminal._

```bash
bash demo/run_connectors.sh
```

- This launches all configured connector servers in the background.
- You should see log output for each entity streaming live as data is generated.

---

## Step 2: Run the Pipeline (L0–L3)

_Open a new terminal._

```bash
python demo/run_demo.py
```

- The demo script will:
    - Check each connector for health
    - Aggregate and align resource and journal streams per entity
    - Infer hierarchy and groupings
    - Apply programmable labeling functions to detect failure classes
    - Write labeled event windows in `data/labeled/` for each entity

- Live, color-coded console output shows resource/journal record counts, hierarchy, labels, and window status for each entity.

---

## Step 3: Model Training and Inference

Once labeled data exist (`data/labeled/*.jsonl`), you can run model training and batch or real-time probabilistic inference.

```bash
python models/_probcast_dual_model_fusion_Version1.py
```


- The model will auto-discover labeled JSONL events, train the full L4/L5 path, and run model inference for all windows/entities.
- Model artifacts and predictions are output to `models/` and/or `data/`.

---

## Expected Outputs

- **Labeled events**: `data/labeled/<entity_id>_*.jsonl` for each entity, each window
- **Console output**: resource & log record counts, group info, labels, pool context for each window
- **Model predictions**: risk scores, class probabilities, and uncertainty for each window and entity
- **Dashboard**: live tables of risk and trend plots by entity

---

## Troubleshooting

- If any connector shows as `[DOWN]` in status: check that all processes in `demo/run_connectors.sh` started successfully and do not conflict on ports.
- If "Both streams: ✗" for an entity: ensure its mock connector is configured and running and is emitting both resource and journal streams.
- If labeled events are missing or incomplete: check log output for failed labeling functions or missing resource/journal records.
- To change entity topology, failure regimes, or baseline config for mock connectors, edit `config/connectors.yaml`.

---


**ProbCast:** End-to-end probabilistic failure forecasting on real (or mock) telemetry—infrastructure-scale, demo-ready.
