# SwiftForecast MCP Service

Containerized Python MCP server for B2B ERP sequence forecasting. Agents can either call fixed forecast tools directly, use `erp_adaptive_forecast_plan` to choose greedy vs beam search, or use `erp_real_sequence_forecast` when the CTO NDA bundle is mounted.

## Local Run

```bash
cd services/mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn erp_forecast.server:app --reload --port 8000
```

The Docker image uses Python 3.11 because the reference notebook requested Python 3.11.x.

Seeded bearer tokens:

- `demo_northstar_full`
- `demo_northstar_read`
- `demo_apex_full`

The MCP endpoint is `http://localhost:8000/mcp`.

## Optional Real Model Artifacts

Do not commit the NDA artifacts. Mount or copy them into the runtime and point `REAL_MODEL_ARTIFACT_DIR` at that directory:

```bash
export REAL_MODEL_ARTIFACT_DIR="/path/to/Public Hackathon (NDA required)"
uvicorn erp_forecast.server:app --reload --port 8000
```

The folder must contain:

- `landing_page_model.onnx`
- `multi_client_dataset.joblib`
- `alit_backend.py`
- `pyarmor_runtime_000000`

`erp_real_sequence_forecast` follows the notebook flow: client `nexus_lab_solutions`, vector size `128`, max sequence length `512`, `temperature`, `top_k`, `max_generate`, and no repeated generated products. The protected backend is treated as a black-box public interface.

## Health Check

```bash
curl http://localhost:8000/healthz
```

## MCP Tool Call Shape

```json
{
  "jsonrpc": "2.0",
  "id": "forecast-1",
  "method": "tools/call",
  "params": {
    "name": "erp_forecast_orders",
    "arguments": {
      "tenant_id": "tenant_northstar",
      "sku": "NSI-VAL-100",
      "customer_segment": "all",
      "horizon_weeks": 12,
      "api_token": "demo_northstar_full"
    }
  }
}
```

## Adaptive Challenge Tool

Use this as the main MCP entry point for the hackathon challenge:

```json
{
  "jsonrpc": "2.0",
  "id": "adaptive-1",
  "method": "tools/call",
  "params": {
    "name": "erp_adaptive_forecast_plan",
    "arguments": {
      "tenant_id": "tenant_northstar",
      "sku": "NSI-VAL-100",
      "objective": "I visit this customer next week. What three products should I prepare for?",
      "recommendation_count": 3,
      "api_token": "demo_northstar_full"
    }
  }
}
```

The response includes the selected decoder plan. Examples:

- `strategy=greedy`, `horizon_weeks=1` for the single most likely next order.
- `strategy=beam_search`, `beam_width=4`, `temperature=1.0` for ranked demand scenarios.
- Lower `temperature` for conservative inventory planning.
- Higher `temperature` for substitute or alternative-product exploration.

## Real Sequence Forecast Call

```json
{
  "jsonrpc": "2.0",
  "id": "real-1",
  "method": "tools/call",
  "params": {
    "name": "erp_real_sequence_forecast",
    "arguments": {
      "client_id": "nexus_lab_solutions",
      "max_generate": 30,
      "temperature": 1.0,
      "top_k": 30,
      "seed": 0,
      "api_token": "demo_northstar_full"
    }
  }
}
```
