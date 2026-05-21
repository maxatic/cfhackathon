"""Warm-latency benchmark for the seven Lane A MCP tools.

Hits the running Starlette REST mirror so the same code path the dashboard
and the demo agent exercise is measured. For each tool the script issues
one warm-up call, then times three subsequent calls and prints the table.
The ONNX session and the SimulationDataset live in module-level singletons
inside `real_model.py`; if either reloads per call the warm numbers will
spike and reveal the regression.

Usage:
    python services/mcp/scripts/bench_tools.py --base http://localhost:8000

The script exits non-zero if any warm call exceeds 1500 ms.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    label: str
    endpoint: str
    method: str
    payload: dict[str, Any] | None
    query: str = ""


WARM_LATENCY_BUDGET_MS = 1500
SAMPLES_PER_TOOL = 3

CALLS: list[ToolCall] = [
    ToolCall(
        "predict_next_basket",
        "/api/predict",
        "POST",
        {"max_generate": 6, "top_k": 5, "temperature": 1.0, "seed": 42},
    ),
    ToolCall(
        "predict_scenarios",
        "/api/scenarios",
        "POST",
        {"beam_width": 3, "horizon": 8, "temperature": 1.0},
    ),
    ToolCall(
        "forecast_plan",
        "/api/forecast-plan",
        "POST",
        {"objective_text": "show three scenarios", "horizon_hint": 8},
    ),
    ToolCall(
        "personalize_client",
        "/api/personalize",
        "POST",
        {
            "additional_tokens": ["b_pcr_primers", "b_pcr_master_mix"],
            "max_generate": 6,
            "seed": 7,
        },
    ),
    ToolCall(
        "anonymize_and_tokenize_orders",
        "/api/anonymize",
        "POST",
        {
            "raw_rows": [
                {
                    "product_name": "safety_goggles",
                    "quantity": 2,
                    "customer_name": "Dr Jane Doe",
                    "email": "jane@nexus.example",
                    "ship_to_address": "1 Lab Way",
                },
                {
                    "product_name": "nitrile_gloves",
                    "quantity": 4,
                    "customer_name": "Dr Jane Doe",
                    "email": "jane@nexus.example",
                    "ship_to_address": "1 Lab Way",
                },
            ]
        },
    ),
    ToolCall("list_clients", "/api/clients", "GET", None),
    ToolCall("list_audit_events", "/api/audit", "GET", None, query="limit=20"),
]


def _call(base: str, tool: ToolCall) -> tuple[int, float]:
    url = base.rstrip("/") + tool.endpoint
    if tool.query:
        url = f"{url}?{tool.query}"
    data = None
    headers = {"Accept": "application/json"}
    if tool.payload is not None:
        data = json.dumps(tool.payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=tool.method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.read()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return status, elapsed_ms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument(
        "--budget-ms",
        type=int,
        default=WARM_LATENCY_BUDGET_MS,
        help="Fail if any warm call exceeds this latency.",
    )
    args = parser.parse_args()
    base: str = args.base
    budget_ms: int = args.budget_ms

    print(f"Benchmark against {base} (budget {budget_ms}ms warm)\n")
    print(f"{'tool':35s} {'warm-up':>10s} {'p50':>10s} {'p95':>10s} {'max':>10s}")
    print("-" * 80)

    over_budget: list[tuple[str, float]] = []
    table: list[dict[str, Any]] = []
    for tool in CALLS:
        warm_status, warm_ms = _call(base, tool)
        if warm_status >= 400:
            print(f"{tool.label:35s} HTTP {warm_status} during warm-up. Aborting.")
            return 2
        samples: list[float] = []
        for _ in range(SAMPLES_PER_TOOL):
            status, ms = _call(base, tool)
            if status >= 400:
                print(f"{tool.label:35s} HTTP {status} mid-run. Aborting.")
                return 2
            samples.append(ms)
        samples.sort()
        p50 = statistics.median(samples)
        p95 = samples[-1] if len(samples) < 4 else samples[int(len(samples) * 0.95)]
        worst = max(samples)
        print(
            f"{tool.label:35s} {warm_ms:>9.1f}ms {p50:>9.1f}ms "
            f"{p95:>9.1f}ms {worst:>9.1f}ms"
        )
        table.append(
            {
                "tool": tool.label,
                "warmup_ms": round(warm_ms, 1),
                "p50_ms": round(p50, 1),
                "p95_ms": round(p95, 1),
                "max_ms": round(worst, 1),
                "samples_ms": [round(value, 1) for value in samples],
            }
        )
        if worst > budget_ms:
            over_budget.append((tool.label, worst))

    print()
    print(json.dumps({"results": table, "budget_ms": budget_ms}, indent=2))

    if over_budget:
        print()
        for label, ms in over_budget:
            print(f"OVER BUDGET: {label} warm max {ms:.1f}ms > {budget_ms}ms")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
