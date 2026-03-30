# ProbCast

Hierarchical Probabilistic Failure Forecasting for Multi-Platform Infrastructure

## Overview

ProbCast is a predictive risk system for modern infrastructure. It collects telemetry from different sources (like Prometheus, CloudWatch, systemd journals, and SIEM), normalizes these into a consistent format, constructs a dynamic hierarchy of entities (org, environment, subnet, host), and labels precursor failure windows using programmable rules. Its final outputs are ready-to-train datasets for probabilistic models that can provide early warning risk signals for various types of failures (CPU overloads, memory exhaustion, disk failures, etc.).

**Key features:**
- Multi-source telemetry ingestion (metrics and logs)
- Dynamic entity hierarchy inference
- Programmatic labeling with weak supervision
- Modular connectors for real or simulated data
- Output: structured labeled events per entity
- Demo/testbed pipeline for complete reproducibility

---

## Directory Structure

```
probcast/
├── requirements.txt
├── .env.example
├── README.md                # ← You are here
├── config/
│   └── connectors.yaml      # Registry of data sources and entities
├── connectors/
│   ├── base_server.py
│   ├── mock_server.py       # ← Demo: run this for mock data (port 8101)
│   ├── mock_prometheus.py
│   ├── mock_journal.py
│   ├── mock_cloudwatch.py
│   ├── mock_siem.py
│   ├── real_prometheus.py
│   └── noise.py
├── ingestion/
│   ├── schema.py
│   ├── normalizer.py
│   ├── aggregator.py
│   └── store.py
├── hierarchy/
│   ├── encoder.py
│   ├── matrix.py
│   └── pooling.py
├── labelling/
│   ├── template_miner.py
│   ├── functions.py
│   ├── pipeline.py
│   └── output.py
├── demo/
│   ├── demo_backend.py      # ← Run this for backend processing
│   ├── dashboard.py        # ← Run this for web dashboard (port 8501)
│   ├── run_connectors.sh
│   ├── run_pipeline.sh
│   └── run_demo.py
└── data/
    └── labeled/            # Labeled output files (JSONL) per entity
```

---

## How the Components Work

- **connectors/** — Mock and real data source servers. For quickstart, use `mock_server.py` to provide synthetic telemetry on demand.
- **ingestion/** — Fetches and normalizes all incoming data, ensuring consistent resource and journal record formats.
- **hierarchy/** — Dynamically learns the infrastructure hierarchy (host, subnet, environment, org), necessary for proper pooling and model calibration.
- **labelling/** — Extracts failure signatures from logs and metrics, runs rule-based functions to label windows as "failure" or "normal", and formats final model-ready events.
- **demo/** — High-level scripts to run the backend pipeline, launch the dashboard, and orchestrate the demo/testbed environment.

---

## Setup Instructions

### 1. Environment Setup

Clone the repo and create a fresh virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate                  # Linux/macOS
# venv\Scripts\activate                   # Windows
pip install -r requirements.txt
```

### 2. Start the Mock Telemetry Server

```bash
cd connectors
python mock_server.py
```
The mock server should start up and listen at port **8101**. This provides fake resource metrics and logs for a demo pipeline run.

### 3. Start the Backend Pipeline

In a new terminal (with the environment activated):

```bash
cd demo
python demo_backend.py
```
This runs the end-to-end aggregation, hierarchy inference, and labeling pipeline. It reads from the configured connector (the mock server above), dynamically infers the entity hierarchy, performs programmatic labeling, and writes labeled events to `data/labeled/`.

### 4. Launch the Dashboard

Again, in a new terminal (and active environment):

```bash
cd demo
python dashboard.py
```
The dashboard should be available at [http://localhost:8501](http://localhost:8501). It visualizes the pipeline status, hierarchy, and labeled signals in real time.

---

## What Each Script Does

- **mock_server.py** (`connectors/`): Synthetic data generator for both resource metrics and log events. Lets you run the pipeline without any real infrastructure.
- **demo_backend.py** (`demo/`): Orchestrates ingestion, hierarchy encoding, and labeling. Produces labeled JSON Lines files (one per entity) as training data for downstream risk models.
- **dashboard.py** (`demo/`): Interactive web UI (usually Streamlit) to visualize incoming telemetry, inferred hierarchy, labeling results, and aggregated risk signals.

---

## Output

- All intermediate and final labeled data is written to `data/labeled/` in JSONL format.  
- Each file = one entity's labeled time windows, containing resource series, log anchors, hierarchy, pooling context, and failure/no-failure tag.

---

## Troubleshooting

- Be sure to activate your Python environment for every terminal (`source venv/bin/activate`).
- The mock server (by default) uses port 8101; the dashboard uses 8501. If you get "address already in use," make sure previous runs are closed.
- Connectors and pipeline scripts must match on entity IDs and configs (`config/connectors.yaml`).

---

## References

- See `PROBCAST_PROJECT_DOCUMENT.md` and `PROBCAST_IMPLEMENTATION_GUIDE.md` for full design, testbed, and architecture details.
- For production, swap in real connectors (`real_prometheus.py`, cloudwatch, etc.) and adjust configs.

---

## Example Quickstart

```bash
# 1. Environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Start mock server
cd connectors
python mock_server.py

# 3. Pipeline backend
cd ../demo
python demo_backend.py

# 4. Launch dashboard (new terminal)
cd demo
python dashboard.py
```

---

If you have issues, check logs for errors, verify configuration in `config/connectors.yaml`, and make sure all servers are running as expected!
