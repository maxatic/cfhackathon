# Swiftron MCP Hackathon Demo

An MCP server that exposes Swiftron's pretrained ONNX order-prediction model to AI agents, plus a Next.js dashboard for the demo. Built for the CF x HHN AI Hackathon (Heilbronn, May 2026).

The model and its dataset come from Swiftron under NDA and are inference-only. We do not train, fine-tune, or retrain it. We expose its real decoding strategies and its sensor-based personalization mechanism through the Model Context Protocol so an agent can use it for procurement planning.

- `services/mcp`: Python FastMCP service that wraps the ONNX model via Swiftron's `SimulationDataset` interface, with greedy and beam-search decoding, sensor-based personalization, PII scrub and tokenization, and an audit log.
- `apps/web`: Next.js dashboard for procurement managers. Shows the predicted next basket, ranked scenarios, and recent tool calls against the live MCP endpoint.
- `artifacts/`: Swiftron's NDA bundle. Gitignored. Each team member mounts their own copy via `REAL_MODEL_ARTIFACT_DIR`.

## What the MCP server exposes

Seven tools, three resources, one prompt. Tool names are locked.

### Tools

| Tool | What it does |
|------|--------------|
| `predict_next_basket` | Autoregressive top-K sampling with uniqueness, returns the next ordered tokens with time deltas. |
| `predict_scenarios` | Real beam search over the ONNX decoder. Returns K ranked trajectories with joint log-probability. |
| `forecast_plan` | Adaptive entry point. The agent passes an objective in natural language, the server picks greedy or beam search and returns the chosen strategy with the result. |
| `personalize_client` | Builds a sensor profile from extra tokens supplied by the agent, then runs prediction with that profile. This uses the model's built-in sensor mechanism. It does not retrain weights. |
| `anonymize_and_tokenize_orders` | Scrubs PII from raw order rows, then maps them into Swiftron's vocabulary. |
| `list_clients` | Lists the client ids the bundled dataset knows about. |
| `list_audit_events` | Returns recent audit events for the demo tenant. |

Every tool call records latency, identity, API-key id, status, and any error summary through `audit.py`.

### Resources and prompt

- `swift://model-card`
- `swift://dataset-card`
- `swift://prediction/latest`
- `procurement_planning_review` (prompt)

## On retraining

The Swiftron bundle is inference-only. There is no training loop, no weight update, no fine-tune path. Rather than fake a retraining lifecycle, we expose the model's real personalization surface: the sensor mechanism, called through `personalize_client`. The agent supplies additional tokens (recent orders, seasonal signals, customer preferences), the server builds a sensor profile, and the next prediction is conditioned on that profile. The underlying ONNX weights are unchanged.

## Quick start

Run the MCP service:

```bash
cd services/mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn erp_forecast.server:app --reload --port 8000
```

Run the dashboard:

```bash
npm install
npm run dev:web
```

Open `http://localhost:3000`.

Run tests:

```bash
npm run test:mcp
```

Health check:

```bash
curl http://localhost:8000/healthz
```

## Mounting the Swiftron bundle

The bundle is distributed privately by the team lead. Unzip it to `<repo-root>/artifacts/` and set in `.env`:

```
REAL_MODEL_ARTIFACT_DIR=/absolute/path/to/cfhackathon/artifacts
```

The directory must contain:

- `landing_page_model.onnx`
- `multi_client_dataset.joblib`
- `alit_backend.py`
- `pyarmor_runtime_000000/`

Verify with `git status` that none of these appear staged. The `.gitignore` blocks `*.onnx`, `*.joblib`, and the PyArmor runtime folder. If anything from `artifacts/` shows up in `git status`, fix the ignore rules before doing anything else.

## MCP endpoint and auth

Local endpoint:

```
http://localhost:8000/mcp
```

Demo tenant: `nexus_lab_solutions`.

Demo API key, scoped to the locked tools:

```
sk_nexus_lab_forecast_full
```

Auth is a static tenant-scoped bearer token enforced per tool scope. There is no OAuth flow, no JWKS validation, no multi-tenant lookup. The demo runs one tenant.

## Example call

`forecast_plan` is the primary demo tool. It is what a procurement-planning agent would call.

```json
{
  "client_id": "nexus_lab_solutions",
  "objective_text": "I visit this customer next week. What three products should I prepare for?",
  "api_token": "sk_nexus_lab_forecast_full"
}
```

The response includes the chosen decoding strategy, a short rationale, and the prediction payload.

## Deployment shape

- `apps/web`: Vercel.
- `services/mcp`: a container host (Railway, Render, Fly.io, or Cloud Run). The MCP service is a long-running Python HTTP service and is not suited to serverless. The Swiftron bundle must be mounted into the container at the path `REAL_MODEL_ARTIFACT_DIR` points to.

## What is intentionally not in the repo

- The Swiftron ONNX file, dataset, and PyArmor runtime. They are NDA-protected and live only under `artifacts/`.
- A training or retraining pipeline. The model is inference-only.
- Synthetic data paths in production code. The MCP server calls the real model or raises.
- OAuth, Supabase JWKS validation, and multi-tenant scope. Out of scope for this demo.
