# ProbCast Demo: Quick Start & Pipeline Walkthrough

This README guides you through running the ProbCast demo pipeline (L0–L2), from environment setup to generating labeled outputs. ProbCast ingests simulated infrastructure telemetry, builds an entity hierarchy, creates programmatic failure labels, and outputs model-ready data. If you want to see how to go from raw metrics and logs to clean, labeled samples for probabilistic risk modeling—this explains every step.

---

## 1. What is ProbCast?

ProbCast is an infrastructure risk forecasting system. It gathers real-time metrics and event logs from diverse sources (mocked here for the demo), infers the hierarchy (hosts → subnets → environments), and programmatically labels failure events, writing output that's ready for model training.

The full system (L0–L6) spans from ingestion to hierarchical probabilistic modeling; this demo gives you L0 (ingestion), L1 (dynamic hierarchy), and L2 (labelling).

---

## 2. Project Structure

```
probcast/
│
├── requirements.txt
├── .env.example
├── README.md
│
├── config/
│   └── connectors.yaml
├── connectors/
│   ├── mock_prometheus.py
│   ├── mock_journal.py
│   ├── mock_cloudwatch.py
│   ├── mock_siem.py
│   └── real_prometheus.py
├── ingestion/       # L0
├── hierarchy/       # L1
├── labelling/       # L2
├── demo/
│   ├── run_connectors.sh
│   └── run_demo.py
└── data/
    └── labeled/
```

---

## 3. Environment Configuration (`.env`)

You **must** have a `.env` file in the project root before running anything.

Here's the absolute minimum:

```env
MOCK_PROMETHEUS_PORT=8001
POLL_INTERVAL=60
```

- `MOCK_PROMETHEUS_PORT` – Port where the mock Prometheus connector runs (default: 8001).
- `POLL_INTERVAL` – Polling interval for ingesting new telemetry, in seconds (default: 60).

Most users will want:

```bash
cp .env.example .env
```

…and then edit your `.env` as needed. The `.env.example` covers all available config options, including additional connector ports, output directory, Prometheus endpoint for real data, and log level.

---

## 4. Setup Instructions

**Python 3.10+** is required.

1. **Clone & install dependencies:**
   ```bash
   git clone <repo-url>
   cd probcast
   python3 -m venv venv
   source venv/bin/activate           # or venv\Scripts\activate (Windows)
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env as needed (see above)!
   ```

---

## 5. Running the Demo

### Step 1. Start the mock connector servers (Terminal 1)

Each telemetry source runs as a separate FastAPI server.

```bash
source venv/bin/activate
bash demo/run_connectors.sh
```

You should see:

```
Starting mock connector servers...
mock_prometheus started on :8001 (PID ...)
mock_journal started on :8002 (PID ...)
mock_cloudwatch started on :8003 (PID ...)
mock_siem started on :8004 (PID ...)

All connectors running. Press Ctrl+C to stop all.

[mock_prometheus:8001] payments-prod-01 | cpu=0.342 mem=0.503 | t=...
[mock_journal:8002]   payments-prod-01 | INFO | sshd.service | Accepted publickey...
...
```

**Leave this terminal open while the demo pipeline runs.**

---

### Step 2. Run the main demo pipeline (Terminal 2)

Open another terminal, activate your environment, and launch:

```bash
cd probcast
source venv/bin/activate
python demo/run_demo.py
```

This runs the full live pipeline:

- L0: Collects and normalizes metrics and logs for each entity
- L1: Builds the entity hierarchy and aggregation matrix
- L2: Applies labeling functions, creates and writes labeled samples

You'll see detailed rich console output for each pipeline stage, including entity resource summaries, pool membership, spotted failure anchors, and output paths.

---

## 6. Where To Find Your Labeled Output

Successful runs write labeled samples to `data/labeled/`. One `.jsonl` file per entity, each line a labeled event window.

Check:

```bash
ls data/labeled/
cat data/labeled/payments-prod-01_*.jsonl | jq .
```

Each entry includes all the context: windowed resource series, log events, assigned label and class, hierarchical and pooling info.

---

## 7. What to Expect

- **Entities with injected failures** (see `config/connectors.yaml`) get proper labels (`cpu_overload`, `memory_exhaustion`, etc).
- **Normal entities** still get windowed files, just with label: `null`.
- **Output then feeds directly into the probabilistic model layers (L4/L5).**

Sample output:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L2 — Labeled Events
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Entity: payments-prod-01
  Label:      cpu_overload
  Confidence: 0.94
  Window:     T-60min → T
  Anchor:     2024-01-15 14:30:00 UTC
  Pool:       subnet-payments | outlier (entity diverges from group mean by 2.3σ)
  Written:    data/labeled/payments-prod-01_<timestamp>.jsonl
```

---

## 8. Troubleshooting

- **Connectors won't start:** Make sure the ports in `.env` aren't already in use.
- **No `data/labeled/` output:** Validate connectors are running (try `curl localhost:8001/health`) and pipeline completed L2.
- **Timestamps or confidence seem strange:** Each demo run injects failure at a slightly different (configurable) offset.

---

## 9. What Next?

- This demo covers up to automated labeling (L2).
- For full training and inference with the probabilistic core (L4/L5/L6), see `PROBCAST_IMPLEMENTATION_GUIDE.md` and `PROBCAST_PROJECT_DOCUMENT.md`.
- To swap in a real connector, implement its FastAPI server (see `connectors/base_server.py`) and update `config/connectors.yaml`.

---

## 10. Architecture — How It Fits Together

The following PlantUML diagram summarizes the data flow.

