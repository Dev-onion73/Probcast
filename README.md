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
cp .env.example .env
```

### 2. **Start All Connector Servers**

In one terminal:
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

Labeled output files appear in `data/labeled/*.jsonl` for each eligible entity.

---

## Directory Structure

```text
Probcast/
├── config/
│   └── connectors.yaml         # Registry of all connectors/entities
├── connectors/                 # Mock and (optionally real) data sources
│   ├── mock_prometheus.py
│   ├── mock_journal.py
│   ├── mock_cloudwatch.py
│   ├── mock_siem.py
│   └── real_prometheus.py
├── ingestion/                  # L0: Normalization/aggregator logic
│   ├── aggregator.py
│   ├── normalizer.py
│   ├── schema.py
│   └── store.py
├── hierarchy/                  # L1: Hierarchy graph, pooling, S matrix
│   ├── encoder.py
│   ├── matrix.py
│   └── pooling.py
├── labelling/                  # L2: Template mining, labelling, output
│   ├── template_miner.py
│   ├── functions.py
│   ├── pipeline.py
│   └── output.py
├── demo/
│   ├── run_connectors.sh
│   └── run_demo.py
├── data/
│   └── labeled/                # L2 output files
├── requirements.txt
├── .env.example
├── README.md
└── PROBCAST_IMPLEMENTATION_GUIDE.md
```

---

## Protocol Layers

| Layer | Purpose |
|-------|---------|
| L0    | Ingests, normalizes, aligns streams from all connectors. Enforces dual-stream contract per entity. |
| L1    | Dynamically infers entity hierarchy, constructs sparse aggregation matrix, computes pooling weights for each group. |
| L2    | Applies Drain template mining to logs and programmatic labeling rules. Emits a model-ready labeled dataset. |
| L3    | (Optional) Synthetic dataset builder for large-scale or augmentation testing (see docs). |
| L4+   | Probabilistic models for risk inference (not included in the repo). |

---

## Usage: Demo Pipeline

**Connector and Source Registry:**  
- All connectors and their entities are registered in `config/connectors.yaml`.  
- To add a new (mock or real) data source, implement as a FastAPI server, add to registry.

**Entity Metadata:**  
- Each entity (host/service) must provide both a metric and a log stream.  
- Metadata needed: `host`, `subnet`, `environment`, `org`.

**Pipeline Execution:**  
1. Run connectors (simulated or real).
2. Start the demo pipeline (`run_demo.py`), which:
   - Checks all connectors.
   - Polls all eligible entities for resource and log events.
   - Normalizes and aligns streams.
   - Infers groupings, computes pooling.
   - Labels failure class and anchor for each window.
   - Writes output to `data/labeled/*.jsonl`.

**Analysis & Model Training:**  
- Use the labeled JSONL files for experimentation, model fitting in Pyro or PyTorch, or as a basis for synthetic batch generation.

---

## Data Flow Example

### L0: Entity telemetry (paired metric + log records)

```json
{
  "entity_id": "payments-prod-01",
  "resource_records": [ /* ...per-timestep metrics... */ ],
  "journal_records":  [ /* ...events with time, level, message... */ ],
  "metadata": {
    "host":        "payments-prod-01",
    "subnet":      "subnet-payments",
    "environment": "production",
    "org":         "acme-corp"
  }
}
```

### L1: Pooling context and aggregation matrix (pooled over e.g. subnet, env)

```json
{
  "entity_id": "payments-prod-01",
  "pool_context": {
    "subnet_mean_cpu": 0.61,
    "subnet_entity_count": 2,
    "pooling_weight": 0.73
  },
  "hierarchy": {
    "host": "payments-prod-01",
    "subnet": "subnet-payments",
    "environment": "production",
    "org": "acme-corp"
  }
}
```

### L2: Labeled sample (model training window)

```json
{
  "entity_id": "payments-prod-01",
  "failure_class": "cpu_overload",
  "failure_timestamp": 1741234567.0,
  "window_start": 1741230967.0,
  "window_end": 1741234567.0,
  "hierarchy": { ... },
  "pool_context": { ... },
  "resource_series": { "cpu_usage": [0.74,0.86,...] },
  "journal_series": [
    {"offset_seconds": 0, "level": "CRITICAL", "unit": "kernel", "message": "CPU overload: ..."}
  ],
  "label": "cpu_overload",
  "confidence": 1.0
}
```

---

## Development & Extension

- To add new connectors: inherit from `connectors/base_server.py`, implement a FastAPI service, add to `config/connectors.yaml`.
- To add new failure signatures: extend labelling functions in `labelling/functions.py`.
- To adapt for real data: swap mock connector implementations for wrappers around actual APIs (see guide Section 14).
- For full probabilistic modeling: feed labeled windows to a Pyro training script (L4/L5 not contained in this repo).

---

*For further questions and contributions, please raise an issue or submit a pull request!*
