#!/bin/bash
# Starts all mock connector servers in background
# Each server logs to its own named output

set -e
source .env

echo "Starting mock connector servers..."

python connectors/mock_prometheus.py &
PIDS+=($!)
echo "mock_prometheus started on :${MOCK_PROMETHEUS_PORT} (PID $!)"

python connectors/mock_journal.py &
PIDS+=($!)
echo "mock_journal started on :${MOCK_JOURNAL_PORT} (PID $!)"

python connectors/mock_cloudwatch.py &
PIDS+=($!)
echo "mock_cloudwatch started on :${MOCK_CLOUDWATCH_PORT} (PID $!)"

python connectors/mock_siem.py &
PIDS+=($!)
echo "mock_siem started on :${MOCK_SIEM_PORT} (PID $!)"

echo ""
echo "All connectors running. Press Ctrl+C to stop all."

# Trap to kill all on exit
trap "kill ${PIDS[*]}" EXIT
wait