#!/usr/bin/env python
"""
Observability system test script.

Functions:
1. Generate structured logs to logs/ditto.jsonl
2. Send test metrics to VictoriaMetrics
3. Demonstrate Tracing functionality
"""

import json
import random
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure log directory exists
log_dir = Path(__file__).parent.parent.parent / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

log_file = log_dir / "ditto.jsonl"


def generate_log_entry() -> dict[str, Any]:
    """Generate a random log entry."""
    services = ["data", "engine", "rotation", "backtest", "risk"]
    levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
    events = [
        "data_fetch_start",
        "data_fetch_complete",
        "factor_calculation",
        "portfolio_rebalance",
        "risk_check",
        "order_submitted",
        "backtest_started",
        "backtest_completed",
    ]

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": random.choice(levels),
        "logger": f"ditto.{random.choice(services)}",
        "function": random.choice(
            [
                "fetch_data",
                "calculate_factors",
                "rebalance",
                "check_risk",
                "run_backtest",
            ]
        ),
        "line": random.randint(1, 500),
        "message": f"Test log message - {random.choice(events)}",
        "service": "ditto",
        "event": random.choice(events),
        # Additional business fields
        "portfolio_id": f"port_{random.randint(1000, 9999)}",
        "symbols_count": random.randint(10, 100),
        "records_processed": random.randint(1000, 10000),
        "duration_ms": random.uniform(10, 500),
    }


def write_logs(count: int = 50) -> None:
    """Write test logs to file."""
    print(f"Writing {count} test log entries to {log_file}...")
    with log_file.open("a", encoding="utf-8") as f:
        for _ in range(count):
            entry = generate_log_entry()
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("✓ Log write complete")


def send_metrics_to_vm() -> None:
    """Send test metrics directly to VictoriaMetrics."""
    # Generate test metrics
    timestamp_ms = int(time.time() * 1000)

    # Prometheus exposition format: metric{labels} value timestamp\n
    metrics = []

    # 1. Service status metrics
    metrics.append(
        f'up{{job="ditto",service="data",instance="localhost"}} 1 {timestamp_ms}'
    )
    metrics.append(
        f'up{{job="ditto",service="engine",instance="localhost"}} 1 {timestamp_ms}'
    )
    metrics.append(
        f'up{{job="ditto",service="rotation",instance="localhost"}} 1 {timestamp_ms}'
    )

    # 2. Kill Switch level
    kill_switch_level = random.choice([0, 1, 2, 3])
    metrics.append(f"ditto_risk_kill_switch_level {kill_switch_level} {timestamp_ms}")

    # 3. Portfolio drawdown
    drawdown = random.uniform(0, 0.2)
    metrics.append(f"ditto_portfolio_drawdown {drawdown:.6f} {timestamp_ms}")

    # 4. Total data records
    records_total = random.randint(10000, 50000)
    metrics.append(f"ditto_data_records_total {records_total} {timestamp_ms}")

    # 5. Data processing rate
    rate_value = random.uniform(10, 100)
    metrics.append(
        f'ditto_data_records_rate{{service="data"}} {rate_value:.2f} {timestamp_ms}'
    )

    # 6. Error count
    ERROR_PROBABILITY = 0.2  # 20% probability of errors
    if random.random() < ERROR_PROBABILITY:
        errors = random.randint(1, 10)
        metrics.append(
            f'ditto_data_errors_total{{service="data"}} {errors} {timestamp_ms}'
        )

    body = "\n".join(metrics)

    print(f"\nSending {len(metrics)} metrics to VictoriaMetrics...")
    try:
        # Use /api/v1/import endpoint for plain text format
        req = urllib.request.Request(
            "http://localhost:8428/api/v1/import/prometheus",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "text/plain",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status in {204, 200}:
                print("✓ Metrics sent successfully")
            else:
                print(f"✗ Metrics send failed: HTTP {response.status}")
    except Exception as e:
        print(f"✗ VictoriaMetrics connection failed: {e}")
        print("  Hint: Ensure service is running at http://localhost:8428")


def query_metrics_from_vm() -> None:
    """Query metrics from VictoriaMetrics to verify data was written."""
    # List all metric names
    labels_url = "http://localhost:8428/api/v1/label/__name__/values"

    print("\nQuerying metrics from VictoriaMetrics...")
    try:
        with urllib.request.urlopen(labels_url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                metric_names = data.get("data", [])
                ditto_metrics = [
                    m for m in metric_names if m.startswith("ditto_") or m == "up"
                ]
                print("✓ Query successful, found metrics:")
                for m in ditto_metrics:
                    print(f"  - {m}")

                # Query value of one metric
                if ditto_metrics:
                    query_url = (
                        f"http://localhost:8428/api/v1/query?query={ditto_metrics[0]}"
                    )
                    with urllib.request.urlopen(query_url, timeout=5) as val_response:
                        val_data = json.loads(val_response.read().decode("utf-8"))
                        if val_data.get("data", {}).get("result"):
                            result = val_data["data"]["result"][0]
                            value = result.get("value", [])
                            if len(value) > 1:
                                print(f"\n  Latest value: {value[1]}")
            else:
                print("✗ No metrics found")
    except Exception as e:
        print(f"✗ Query failed: {e}")


def print_grafana_urls() -> None:
    """Print Grafana and other service access URLs."""
    print("\n" + "=" * 60)
    print("Observability Service Access URLs:")
    print("=" * 60)
    print("  Grafana:          http://localhost:3000")
    print("  VictoriaMetrics:  http://localhost:8428")
    print("  VictoriaLogs:     http://localhost:9428")
    print("  Vector:           http://localhost:8686")
    print("=" * 60)

    print("\nGrafana Pre-configured Datasources:")
    print("  - VictoriaMetrics (Prometheus compatible)")
    print("  - VictoriaLogs")

    print("\nVictoriaLogs Query Example:")
    print('  Enter query at http://localhost:9428: {service="ditto"}')

    print("\nVictoriaMetrics Query Example:")
    print('  Query in Grafana or http://localhost:8428: up{job="ditto"}')
    print("=" * 60)


def main() -> None:
    """Main function."""
    print("=" * 60)
    print("Ditto Observability System Test")
    print("=" * 60)

    # 1. Write logs
    write_logs(count=100)

    # Wait for Vector to collect logs
    print("\nWaiting for Vector to collect logs...")
    time.sleep(3)

    # 2. Send metrics
    send_metrics_to_vm()

    # Wait for metrics to be written
    time.sleep(1)

    # 3. Query verification
    query_metrics_from_vm()

    # 4. Print access info
    print_grafana_urls()

    print("\nTest complete!")
    print("Hint: Log file located at:", log_file)
    print("Hint: Vector will automatically collect log files and send to VictoriaLogs")


if __name__ == "__main__":
    main()
