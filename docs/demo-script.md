# Demo Script

## Setup

1. Start the MCP service: `docker compose up --build mcp`
2. Start the dashboard: `npm run dev:web`
3. Open `http://localhost:3000`
4. In an MCP client, connect to `http://localhost:8000/mcp` with bearer token `demo_northstar_full`

## Storyboard

1. Open the dashboard on `NSI-VAL-100`, segment `all`, 12 weeks.
2. Run a forecast and point to forecast units, revenue, SMAPE, and MAE.
3. Ask the agent:

```text
Use the SwiftForecast MCP server. I am visiting a Northstar Industrial customer next week.
For tenant_northstar and SKU NSI-VAL-100, decide whether to use greedy search, beam search,
or a longer inventory forecast. Tell me the three products I should prepare for, the demand
scenarios behind that recommendation, and any customer risk I should know about.
```

4. Show the MCP tools:
   - `erp_forecast_orders`
   - `erp_beam_search_forecast`
   - `erp_adaptive_forecast_plan`
   - `erp_rank_at_risk_customers`
   - `erp_anonymize_orders`
   - `erp_trigger_retraining`
   - `erp_get_retraining_status`
   - `erp_list_model_versions`
5. Show resources:
   - `erp://dataset-card`
   - `erp://model-card`
   - `erp://forecast/latest`
6. Close with the distribution story: Vercel hosts the dashboard, Supabase holds tenant metadata with RLS, and the MCP/model service runs as a container.

Narration line:

```text
The model is still just a sequence forecaster: product/order history in, next tokens out. The MCP layer is what turns it into a flexible agent tool. The agent can pick greedy decoding for a single next call, beam search for alternatives, lower temperature for inventory planning, or higher temperature when it wants substitute ideas.
```

## Real CTO Model Moment

If the NDA bundle is mounted, call `erp_real_sequence_forecast` for `nexus_lab_solutions`:

```json
{
  "client_id": "nexus_lab_solutions",
  "max_generate": 30,
  "temperature": 1.0,
  "top_k": 30,
  "seed": 0,
  "api_token": "demo_northstar_full"
}
```

Narration line:

```text
This is the provided ONNX sequence model behind the same MCP surface. We are not inspecting the protected transformation code; we mount the artifact bundle, call the public SimulationDataset interface, and let the agent steer temperature, top-k, and generation length.
```

## Adaptive Forecast Call

```json
{
  "tenant_id": "tenant_northstar",
  "sku": "NSI-VAL-100",
  "objective": "I visit this customer next week. What three products should I prepare for?",
  "recommendation_count": 3,
  "api_token": "demo_northstar_full"
}
```

Expected response highlights:

- `selected_strategy`: `beam_search`
- `decoder_plan`: horizon, beam width, temperature, and reason
- `scenarios`: ranked sequence forecasts
- `customer_risk`: anonymized risky customer refs
- `products_to_prepare`: three product recommendations

## Retraining Moment

1. Call `erp_forecast_orders` for `tenant_northstar`, `NSI-VAL-100`, 12 weeks and note the first forecast quantity.
2. Call `erp_trigger_retraining` with reason `new anonymized customer orders landed overnight`.
3. The trigger response should be `queued` and include the first loss point plus before/after metrics.
4. Poll `erp_get_retraining_status` once. The job should be `running` with a partial deterministic loss curve.
5. Poll `erp_get_retraining_status` again. The job should be `completed`, include the full loss curve, activate a new model version, and return a `forecast_shift`.
6. Re-run `erp_forecast_orders`. The model version should change and the forecast should visibly shift because the tenant adapter is now active.

Narration line:

```text
The base model stayed frozen. The tenant adapter trained on anonymized recent orders, produced a visible loss curve, activated a new model version, and shifted the forecast without exposing raw customer identities.
```

## Fallback

If the MCP client is unavailable, the dashboard still renders a local forecast and the service can be shown through:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/.well-known/oauth-protected-resource
```

## Customer-Risk Call

```json
{
  "tenant_id": "tenant_northstar",
  "sku": "NSI-VAL-100",
  "horizon_weeks": 12,
  "limit": 5,
  "api_token": "demo_northstar_full"
}
```

## Retraining Call

```json
{
  "tenant_id": "tenant_northstar",
  "reason": "new anonymized customer orders landed overnight",
  "api_token": "demo_northstar_full"
}
```
