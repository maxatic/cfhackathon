# Demo Script

## Setup

1. Start the MCP service: `docker compose up --build mcp`
2. Start the dashboard: `npm run dev:web`
3. Open `http://localhost:3000`
4. In an MCP client, connect to `http://localhost:8000/mcp`
5. Use bearer token `demo_nexus_lab_full`

## Three-Minute Story

Lead with the customer question:

```text
NexusLab Solutions has a lab visit next week. What should procurement prepare?
Show the likely next basket, two alternate scenarios, and whether the lab profile changes the answer.
```

Narration:

```text
NexusLab is a chemistry research lab. Their procurement team does not want model controls.
They want a clear answer before a supplier visit: what should be ready, what could change, and what data stayed protected.
```

## Demo Flow

1. Open the dashboard on `nexus_lab_solutions`.
2. Run `predict_next_basket`.
3. Point to the generated basket and time deltas.
4. Run `predict_scenarios`.
5. Compare ranked trajectories by joint log probability.
6. Run `forecast_plan` with the visit question.
7. Show the selected decoder strategy and recommendation summary.
8. Run `personalize_client` with a short lab-profile token list.
9. Compare before and after baskets.
10. Run `anonymize_and_tokenize_orders`.
11. Show hashed fields, scrubbed fields, tokenized rows, and time deltas.
12. Close on audit events.

## Tool Calls To Show

- `predict_next_basket`: answers the most likely next order basket.
- `predict_scenarios`: shows ranked alternate baskets with joint log probability.
- `forecast_plan`: lets the agent pick the decoder path from the user intent.
- `personalize_client`: shifts the prediction with a session sensor profile.
- `anonymize_and_tokenize_orders`: scrubs raw rows before token mapping.
- `list_clients`: confirms the demo client.
- `list_audit_events`: proves calls are recorded.

Resources:

- `swift://model-card`
- `swift://dataset-card`
- `swift://prediction/latest`

Prompt:

- `procurement_planning_review`

## Main Agent Prompt

```text
Use the SwiftForecast MCP server for client nexus_lab_solutions.
I am visiting this lab next week. Tell me what procurement should prepare.
Give me the likely next basket, two alternate scenarios, and a short explanation I can give the account owner.
Before quoting uploaded rows, scrub and tokenize them.
```

Expected answer:

- A basket prediction with generated tokens and time deltas.
- Two or more scenario paths, ranked by joint log probability.
- A plain procurement recommendation.
- A privacy report for any uploaded rows.
- A recent audit event for each tool call.

## Fallback If A Live Tool Fails

Keep the story intact. Say:

```text
The local dashboard has cached demo responses, but the server response is the source of truth.
The panel is showing the same response shape that the MCP tool returns.
```

Then show:

```bash
curl http://localhost:8000/healthz
```

## Closing Line

```text
The customer asks one procurement question. The agent chooses the model call, runs the decoder, protects uploaded rows, and leaves an audit trail.
```
