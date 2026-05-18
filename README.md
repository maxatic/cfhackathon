# SwiftForecast MCP Hackathon Demo

MCP-first sequence forecasting demo for the Swifttron challenge. The core idea is not to expose one fixed "forecast this SKU" API. Instead, an AI agent talks to an MCP server that can decide how to call the sequence model for a business goal: greedy next-product prediction, beam-search scenarios, higher-temperature alternatives, longer-horizon inventory planning, or customer-visit preparation.

- `services/mcp`: Python FastMCP service with synthetic ERP data, autoregressive forecasts, controllable beam search, an adaptive forecast-planning tool, anonymization, retraining metadata, and Docker packaging.
- `apps/web`: Next.js dashboard for forecast review, model status, MCP connection details, and demo orchestration.
- `supabase`: Postgres schema, RLS policies, and seed data for the SaaS metadata layer.
- `docs`: demo script and agent prompts.

## Challenge Scope

Build a nanodocker-style MCP service around the provided sequence forecaster so other agents can use the model flexibly. Keep the client fixed to the seeded demo tenant and do not spend time optimizing model quality; the supplied model is intentionally an early-training checkpoint. The differentiator is the MCP/agent control layer:

- Let an agent choose greedy search when it needs the single most likely next product/order.
- Let an agent choose beam search when it needs multiple plausible future sequences.
- Expose `beam_width` and `temperature` so the agent can trade off conservative planning vs more creative alternatives.
- Support business tasks such as "what should I prepare for a customer visit next week?", "forecast the next 50 orders for inventory", and "which customers or products are at risk?"
- Treat encrypted/protected model transformation code as a black box. Do not decrypt or inspect protected IP; call it only through the provided interfaces.

## CTO Bundle Findings

The NDA folder contains the real challenge artifacts:

- `landing_page_model.onnx`: the sequence model.
- `multi_client_dataset.joblib`: preloaded multi-client dataset records.
- `hackathon_inference.ipynb`: reference inference flow.
- `alit_backend.py` and `pyarmor_runtime_000000`: protected backend/dataset classes. Use them as a public interface only.

The notebook's concrete setup is Python 3.11, `onnxruntime`, `numpy`, and `joblib`. It targets client `nexus_lab_solutions`, uses vector size `128`, max sequence length `512`, max catalog size `256`, and generates product/time tokens such as `<dt_1w>`, `s_goggles_basic`, and `c_reag_n_butyllithium`. Its decoder exposes the important agent knobs from the CTO pitch: `temperature`, `top_k`, `max_generate`, and a hard uniqueness constraint that prevents repeating generated products in one basket.

The repo now includes an optional adapter tool, `erp_real_sequence_forecast`, that follows the notebook contract when the NDA bundle is mounted. The protected files are intentionally not committed.

## Quick Start

Run the testable Python core:

```bash
PYTHONPATH=services/mcp python3 -m unittest discover services/mcp/tests
```

Run the MCP service:

```bash
docker compose up --build mcp
```

Run the web app:

```bash
npm install
npm run dev:web
```

Open `http://localhost:3000`. The dashboard will use local demo forecast logic if `MCP_REST_URL` is not configured, and will call the Python service when it is available.

## MCP Endpoint

Local MCP endpoint:

```text
http://localhost:8000/mcp
```

Seeded tenant-scoped API key:

```text
sk_northstar_forecast_full
```

Legacy `demo_northstar_full` still works as a local alias, but the demo story should use the `sk_...` keys because they model B2B customer API keys with tenant and scope bindings. Seeded keys:

- `sk_northstar_forecast_full`: tenant `tenant_northstar`, scopes `forecast`, `anonymize`, `retrain`, `models`, `audit`
- `sk_northstar_forecast_read`: tenant `tenant_northstar`, scopes `forecast`, `models`, `audit`
- `sk_apex_forecast_full`: tenant `tenant_apex`, scopes `forecast`, `anonymize`, `retrain`, `models`, `audit`

Core tools:

- `erp_forecast_orders`
- `erp_beam_search_forecast`
- `erp_adaptive_forecast_plan`
- `erp_real_sequence_forecast` when `REAL_MODEL_ARTIFACT_DIR` is configured
- `erp_rank_at_risk_customers`
- `erp_anonymize_orders`
- `erp_trigger_retraining`
- `erp_get_retraining_status`
- `erp_list_model_versions`
- `erp_list_audit_events`

Every tool call records an in-memory audit event with tool name, tenant, actor, API-key id, status, latency, timestamp, and error summary. `erp_list_audit_events` returns recent tenant-scoped events for the dashboard. Supabase persistence is intentionally left as a production extension.

Retraining is a deterministic demo lifecycle: `erp_trigger_retraining` queues a job, the first `erp_get_retraining_status` poll returns `running` with a partial loss curve, and the second poll returns `completed`, activates a new tenant adapter model version, and shifts subsequent forecasts.

Resources and prompt:

- `erp://dataset-card`
- `erp://model-card`
- `erp://forecast/latest`
- `demand_planning_review`

Primary challenge demo tool:

```json
{
  "tenant_id": "tenant_northstar",
  "sku": "NSI-VAL-100",
  "objective": "I visit this customer next week. What three products should I prepare for?",
  "recommendation_count": 3,
  "api_token": "sk_northstar_forecast_full"
}
```

Call this through `erp_adaptive_forecast_plan`. It returns the selected decoding strategy, horizon, beam width, temperature, ranked beam scenarios, customer risk, and product recommendations.

Optional real-model call after mounting the NDA bundle:

```json
{
  "client_id": "nexus_lab_solutions",
  "max_generate": 30,
  "temperature": 1.0,
  "top_k": 30,
  "seed": 0,
  "api_token": "sk_northstar_forecast_full"
}
```

Set `REAL_MODEL_ARTIFACT_DIR` to the folder containing `landing_page_model.onnx`, `multi_client_dataset.joblib`, `alit_backend.py`, and `pyarmor_runtime_000000`. On Apple Silicon, the provided top-level PyArmor runtime is x86_64; the Linux x86_64 runtime is the safer target for the container demo.

## Auth Scope

The current implementation validates static tenant-scoped API keys and enforces per-tool scopes. It also publishes protected-resource metadata and `WWW-Authenticate` challenges so agents know to send bearer credentials.

This demo does not implement a full OAuth authorization-code flow or Supabase JWKS validation yet. Supabase Auth/JWKS validation is the next production step; the repo should not be described as having completed OAuth login.

## Deployment Shape

- Deploy `apps/web` to Vercel.
- Deploy `services/mcp` as a Docker service on Railway, Render, Fly.io, or Cloud Run.
- Apply `supabase/migrations/202605170001_init.sql` to Supabase and load `supabase/seed.sql` for demo metadata.

Vercel should host only the dashboard. The MCP/model service should run on a container host because it is packaged as a long-running Python HTTP service.
