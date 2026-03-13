# ProbCast: Hierarchical Probabilistic Failure Risk Forecasting

ProbCast is a fully reproducible pipeline for infrastructure failure forecasting using unified, dual-stream telemetry (metrics + event logs) from heterogeneous sources. It supports streaming ingestion, dynamic hierarchy inference, partial statistical pooling, programmatic event labelling, and generates model-ready datasets for advanced Bayesian and deep learning models.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Directory Structure](#directory-structure)
- [Protocol Layers](#protocol-layers)
- [Usage: Demo Pipeline](#usage-demo-pipeline)
- [Data Flow Example](#data-flow-example)
- [Development & Extension](#development--extension)
- [References](#references)

---

## Overview

Modern infrastructure emits diverse telemetry from metrics platforms (Prometheus, AWS CloudWatch), system logs, and security event sources (SIEM). ProbCast collects these via connector servers, normalizes them, dynamically organizes infrastructure into a hierarchy, computes per-entity/group risk context, and labels failure events using weak supervision.

Its core strengths are:

- **Unified streaming ingestion:** Handles multiple platforms and formats, all translated to a canonical schema.
- **Dynamic hierarchy & pooling:** Automatically groups entities (host, subnet, environment, org) with variance-based partial pooling.
- **Programmatic L2 labelling:** Attaches failure labels to time windows by combining metric precursors and event signatures.
- **Model-ready outputs:** L2 emits a labeled dataset for training probabilistic models for calibrated risk forecasting.

---

## Architecture

```text
┌──────────────┬──────────────┬──────────────┬───────────────┐
│ mock_prometheus │ mock_journal │ mock_cloudwatch │ mock_siem (800x) │
└──────────────┴─────┬──────────┴───────┬────┴──────┬───────┘
    [HTTP polling / source registry]    │    │
             ┌──────────────────────────┴────┘
             │
     ┌───────▼────────┐
     │ Aggregator (L0)│
     └───────┬────────┘
             │
     ┌───────▼────────┐
     │  Hierarchy (L1)│
     └───────┬────────┘
             │
     ┌───────▼──────────┐
     │ Labelling (L2)   │
     └───────┬──────────┘
             │
     ┌───────▼─────────────┐
     │ data/labeled/*.jsonl│
     └─────────────────────┘
```

- Each layer matches the [Implementation Guide](./PROBCAST_IMPLEMENTATION_GUIDE.md), running independently for maximum robustness.
- Downstream probabilistic models (L4/L5) consume the L2-labelled dataset.

---

## Quickstart

### 1. **Setup Python Environment**

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

### 3. **Run the Demo End-to-End Pipeline**

In another terminal:
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
- To add new failure signatures: extend labelling functions in `labelling/functions.py` (see [PROBCAST_IMPLEMENTATION_GUIDE.md](./PROBCAST_IMPLEMENTATION_GUIDE.md#12-failure-classes-reference)).
- To adapt for real data: swap mock connector implementations for wrappers around actual APIs (see guide Section 14).
- For full probabilistic modeling: feed labeled windows to a Pyro training script (L4/L5 not contained in this repo).

---

*For further questions and contributions, please raise an issue or submit a pull request!*
