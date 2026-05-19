# Demo Script

## Persona shift

Demo *user* = a sales/supply manager at a B2B distributor selling to research labs. Their customer is NexusLab Solutions. They want to anticipate NexusLab's next order so they can pre-stock, time outreach, and protect margin.

This frames Swiftron's actual commercial pitch: vendors run this MCP inside their own AI agents to forecast what their B2B customers will buy.

## Setup

1. Start the MCP service: `uvicorn erp_forecast.server:app --port 8000 --app-dir services/mcp`
2. Start the dashboard: `npm run dev:web`
3. Open http://localhost:3000
4. In an MCP client (Claude Desktop), connect to http://localhost:8000/mcp
5. Use bearer token `demo_nexus_lab_full`

## Three-minute story

Lead with the vendor's question:

> NexusLab Solutions is one of our top accounts. What are they likely to order next, and what should I have ready before their account manager calls them?

Narration:

> Vendors selling into research labs face the same problem every B2B distributor faces: customers do not share their purchasing plans. Their next order is a guess. Stock too much and margin dies. Stock too little and the customer goes elsewhere. SwiftForecast solves this by predicting the customer's next basket directly. We wrapped Swiftron's model in MCP so any AI agent inside our sales team can call it.

## Demo flow (3 minutes)

**Scene 1 — Setup (25s)**

> "I'm a supply planner at a chemistry distributor. NexusLab is a research lab we sell to. I want my AI agent to tell me what they're likely to order next and how I should prep. Watch."

Open Claude Desktop with our MCP server connected. Open the dashboard side-by-side.

**Scene 2 — Live agent call (75s)**

Type into Claude Desktop:

> "What is NexusLab likely to order next, and what alternative baskets should I consider for next month?"

Agent calls `forecast_plan` → picks beam search, horizon 4, top-K 5. Returns 3 ranked scenarios. Dashboard mirrors the call live.

Walk the audience through the result:
- Rank 1: PPE + lab consumables (goggles, stir bars, vacuum grease) at +14 days. Routine refresh.
- Rank 2: Solvents + gloves (pentane, DCM, nitrile L) at +14 days. Heavier chemistry session ahead.
- Rank 3: Mixed (goggles, stir bars, gloves).

Closer line for the scene:

> "Notice the model ranks scenarios with joint log-probability, not point forecasts. We do not pretend to know exactly what they will order. We surface the three most likely paths. A supply planner can stock against the union of the top two and protect margin without overcommit."

**Scene 3 — Personalization (60s)**

> "Two weeks ago NexusLab expanded their PCR program. They told my account manager. I want to bake that into the forecast."

Click `personalize_client` with new tokens: `b_pcr_tubes`, `b_taq_polymerase`, `b_dntp_set`. Sensor session minted. Same `forecast_plan` call runs again. Predictions visibly shift toward biology supplies.

Closer line:

> "The model never sees the customer's name, address, or order values. It works on the tokenized vocabulary Swiftron defined. That is how a vendor deploys this to their entire customer base without a single NDA renegotiation."

**Scene 4 — Close (20s)**

> "Every B2B distributor has the same problem. Customers will not share their purchasing plans. Swiftron's model solves that. The MCP layer means our sales team's AI agent gets this capability without any of them learning the API. Questions?"

## Tool calls to show

- `predict_next_basket`: most likely next basket with time delta
- `predict_scenarios`: ranked alternate baskets with joint log-probability
- `forecast_plan`: agent picks decoder strategy from intent text
- `personalize_client`: shifts prediction with a session sensor profile
- `anonymize_and_tokenize_orders`: scrubs raw rows before token mapping (use if a judge asks how customer data flows in)
- `list_clients`: confirms 169 clients in the dataset
- `list_audit_events`: proves calls are recorded for compliance

Resources:
- `swift://model-card`
- `swift://dataset-card`
- `swift://prediction/latest`

Prompt:
- `procurement_planning_review`

## Main agent prompt (for Claude Desktop)

```text
You have access to the SwiftForecast MCP server. The user is a supply planner at a B2B chemistry distributor. The customer of interest is nexus_lab_solutions.

When the user asks about what a customer will order, prefer forecast_plan first, then drill into predict_scenarios for alternatives. If the user mentions a customer change or new program, call personalize_client with the relevant tokens. If they paste a CSV of historical orders, call anonymize_and_tokenize_orders before doing anything else.

Respond in short, plain sentences. Quote tokens directly. Mention joint log-probability when comparing scenarios. Do not invent product names beyond the vocabulary returned by the tool.
```

## Q&A defense

**"Is this actually a transformer? Can you show the architecture?"**
> "It is Swiftron's pretrained ONNX model. We treat it as a black box and call it through their `SimulationDataset` interface. We did not modify, decrypt, or inspect the protected code. Our contribution is the MCP wrapper that exposes it to any AI agent."

**"What about retraining?"**
> "Their bundle is inference-only, so we built personalization at inference. A vendor onboards a customer by passing their product list to `personalize_client`, which builds a sensor profile inside the existing model. No fine-tuning, no weight changes, no data sent back to Swiftron. The model adapts to each customer instantly."

**"What is the joint log-probability you keep mentioning?"**
> "Beam search ranks complete trajectories by the product of their token probabilities. We report it as a sum of log-probabilities so it's directly comparable across scenarios. Higher is more likely."

**"How does the vendor integrate this into their stack?"**
> "Two ways. One: their internal AI agent connects to the MCP server like Claude Desktop did just now. Two: they call the REST mirror at `/api/predict`, `/api/scenarios`, etc., from a backend service. We ship both surfaces in the same container."

**"How does it scale to 50,000 customers?"**
> "Each customer is one record in Swiftron's dataset, addressed by `client_id`. The model is the same. Scaling is a question of inference compute, not model retraining. Sensor profiles are cached per session, so personalization is cheap to repeat."

## Fallback if a live tool fails

Story stays intact. Say:

> The dashboard has cached responses that match the live tool shapes. The server is the source of truth, the dashboard is a viewer.

Then show:

```bash
curl http://localhost:8000/healthz
```

If the server is dead too, switch to the recorded video Sherniyaz prepared.

## Closing line

> A vendor asks one customer question. The agent picks the decoder, runs the model, surfaces ranked scenarios, scrubs uploads, and logs every call. That is the difference between an MCP product and an API.
