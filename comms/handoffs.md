# Handoffs

Cross-lane dependencies. When Lane A needs Lane C to ship something, or Lane B needs Lane A to expose a new endpoint, record it here.

Format:

```
- [from-LANE to-LANE] [HH:MM YYYY-MM-DD]
  context: what was done or what's needed
  asks: what the other lane needs to do
  contract: exact function signature and return type
  example: one concrete input and output
  status: pending | accepted | done
```

Lane C runs on Codex with a vibe-coding owner. All contracts handed to Lane C must include concrete examples. Codex generates better code from explicit examples than from abstract specs.

---

## Pre-planned handoffs (locked Sunday, ready for Monday)

### Handoff 1: [C to A] Monday afternoon
context: real_model.py extended to expose autoregressive prediction
asks: Lane A wires this into the `predict_next_basket` MCP tool
contract:
```python
def predict_basket(
    client_id: str,
    start_sequence: list[str] | None,
    max_generate: int = 32,
    top_k: int = 5,
    temperature: float = 1.0,
    seed: int | None = None,
) -> dict:
    """
    Returns:
      {
        "client_id": str,
        "start_sequence": list[str],
        "generated_tokens": list[str],
        "generated_times": list[int],
        "model_version": str,
        "decoder_config": {...},
      }
    """
```
example: 
  input: `predict_basket("nexus_lab_solutions", None, max_generate=8, top_k=5, temperature=1.0, seed=42)`
  output: `{"client_id": "nexus_lab_solutions", "start_sequence": [], "generated_tokens": ["dt_3d", "c_acid_7", "c_solv_12", ...], "generated_times": [3, 0, 0, ...], "model_version": "swiftron-onnx-v1", "decoder_config": {"strategy": "top_k", "k": 5}}`
status: accepted

### Handoff 2: [C to A] Tuesday morning
context: beam_search.py exposes ranked trajectory enumeration
asks: Lane A wires this into `predict_scenarios` MCP tool
contract:
```python
def run_beam(
    client_id: str,
    start_sequence: list[str] | None,
    beam_width: int = 4,
    horizon: int = 16,
    temperature: float = 1.0,
) -> list[dict]:
    """
    Returns ranked list, highest joint log-prob first:
      [
        {
          "rank": int,
          "joint_log_prob": float,
          "tokens": list[str],
          "time_deltas": list[int],
        },
        ...
      ]
    """
```
example:
  input: `run_beam("nexus_lab_solutions", None, beam_width=3, horizon=8)`
  output: `[{"rank": 1, "joint_log_prob": -12.3, "tokens": [...], "time_deltas": [...]}, {"rank": 2, "joint_log_prob": -13.8, ...}, {"rank": 3, "joint_log_prob": -14.1, ...}]`
status: accepted

### Handoff 3: [A to B] Tuesday afternoon
context: REST mirror endpoints live at `/api/predict`, `/api/scenarios`, `/api/personalize`, `/api/anonymize`, `/api/audit`
asks: Lane B wires dashboard panels to these
contract: response shapes match types declared in `apps/web/src/lib/types.ts`. Lane A updates types.ts when each tool ships.
example: Lane B can mock against the type definitions until the live endpoint exists.
status: pending

### Handoff 4: [C to A] Wednesday morning
context: sensor.py exposes per-session personalization
asks: Lane A wires this into `personalize_client` MCP tool
contract:
```python
def apply_sensor(
    client_id: str,
    additional_tokens: list[str],
) -> str:
    """Returns a session_id (string, opaque) tied to a cached sensor profile."""

def predict_with_session(
    session_id: str,
    start_sequence: list[str] | None,
    max_generate: int = 32,
    top_k: int = 5,
    temperature: float = 1.0,
    seed: int | None = None,
) -> dict:
    """Same return shape as predict_basket."""
```
example:
  step 1: `session_id = apply_sensor("nexus_lab_solutions", ["b_dna_kit_3", "b_pcr_master_mix"])`
  step 2: `predict_with_session(session_id, None, max_generate=8)` returns predictions shifted toward biology supplies
status: accepted

### Handoff 5: [C to A] Wednesday afternoon
context: tokenize_orders.py converts raw ERP CSV rows to Swiftron token sequences with PII scrubbed
asks: Lane A wires this into `anonymize_and_tokenize_orders` MCP tool
contract:
```python
def anonymize_and_tokenize(
    raw_rows: list[dict],
    client_id: str,
) -> dict:
    """
    Returns:
      {
        "client_id": str,
        "tokenized": list[str],
        "time_deltas": list[int],
        "audit_report": {
          "row_count": int,
          "fields_hashed": list[str],
          "fields_scrubbed": list[str],
          "detected_sensitive_fields": list[str],
          "k_anonymity_proxy": int,
          "privacy_notes": list[str],
        },
      }
    """
```
example:
  input rows include `customer_name`, `ship_to_address`, `po_number`, plus product SKUs, quantities, dates
  audit_report shows which fields got hashed, scrubbed, bucketed
  tokenized list shows tokens mapped from product SKUs to Swiftron's vocab (with fallback for unknown SKUs)
status: accepted

---

## Active handoffs

- [A to B] [11:50 2026-05-19]
  context: Lane A wired all 6 locked MCP tools + REST mirrors on lane-a-server and smoke-tested every REST route against the real Swiftron bundle on Orkhan's Mac. Endpoints live at `/api/predict`, `/api/scenarios`, `/api/forecast-plan`, `/api/personalize`, `/api/anonymize`, `/api/audit` (GET or POST), `/api/clients` (GET or POST). All require a JSON body (the GET routes accept query params or empty body). Auth: with `MCP_TRUST_TRANSPORT_AUTH=true` the body's `api_token` is optional; otherwise pass `api_token: "demo_nexus_lab_full"` (or set `MCP_DEMO_TOKEN`).
  asks: Update `apps/web/src/lib/mcp-client.ts` to call the new endpoints and use the new response types. The old `requestRealSequence`, `requestForecast`, `requestRisk`, `requestModelVersions`, `triggerRetraining`, `requestRetrainingStatus` should be retired or replaced. Old types (`ForecastRun`, `BeamScenario`, `RiskResponse`, `ModelVersion*`, `RetrainingJob`, `LossPoint`, `AnonymizationResponse`, `AnonymizedOrderSample`, `AnonymizationReport`, `RealSequenceResponse`) can be deleted once you swap to the new ones.
  contract: I added (additively, no deletions) the following TypeScript types in `apps/web/src/lib/types.ts`:
  ```
  DecoderConfig
  PredictNextBasketResponse        -> POST /api/predict
  ScenarioTrajectory
  PredictScenariosResponse         -> POST /api/scenarios
  ForecastPlanResponse             -> POST /api/forecast-plan
  PersonalizeClientResponse        -> POST /api/personalize
  AnonymizeAuditReport
  TokenizedRow
  AnonymizeAndTokenizeResponse     -> POST /api/anonymize
  ListClientsResponse              -> GET or POST /api/clients
  ListAuditEventsResponse          -> GET or POST /api/audit (note: events: AuditEvent[] which already exists)
  ```
  example payloads (live, from smoke test against nexus_lab_solutions):
  ```
  POST /api/predict {"client_id":"nexus_lab_solutions","max_generate":6,"top_k":5,"seed":42}
    -> {"client_id":"nexus_lab_solutions","start_sequence":[],"generated_tokens":["<dt_2w>","s_goggles_basic","s_gloves_neoprene","m_grease_vacuum","m_stir_bar_set","e_oven_drying"],"generated_times":[14,0,0,0,0,0],"model_version":"swiftron-onnx-v1","decoder_config":{"strategy":"top_k","top_k":5,"temperature":1.0,"max_generate":6,"seed":42}}
  POST /api/scenarios {"client_id":"nexus_lab_solutions","beam_width":3,"horizon":4}
    -> {"client_id":"...","scenarios":[{"rank":1,"joint_log_prob":-4.93,"tokens":["<dt_2w>","s_goggles_basic","m_stir_bar_set","m_grease_vacuum"],"time_deltas":[14,0,0,0]}, ...], "model_version":"swiftron-onnx-v1","decoder_config":{"strategy":"beam_search","beam_width":3,"horizon":4,"temperature":1.0}}
  POST /api/forecast-plan {"objective_text":"compare best vs worst case","horizon_hint":4}
    -> {"client_id":"nexus_lab_solutions","chosen_strategy":"beam_search","rationale":"...","payload":{...scenarios payload},"model_version":"swiftron-onnx-v1"}
  POST /api/personalize {"client_id":"nexus_lab_solutions","additional_tokens":["c_solv_pentane","m_stir_bar_set"],"max_generate":5}
    -> {"session_id":"session_<hex>","client_id":"...","additional_tokens":[...],"prediction":{...PredictNextBasketResponse with decoder_config.strategy="sensor_profile"}}
  POST /api/anonymize {"client_id":"nexus_lab_solutions","raw_rows":[{"customer_name":"...","email":"...","product_sku":"c_solv_pentane","order_date":"2026-05-01","quantity":4,"ship_to_address":"..."}]}
    -> {"client_id":"...","tokenized":["c_solv_pentane",...],"time_deltas":[0,7,...],"audit_report":{"row_count":2,"fields_hashed":["customer_name","email"],"fields_scrubbed":["ship_to_address"],"detected_sensitive_fields":[...],"k_anonymity_proxy":1,"privacy_notes":[...]},"rows":[{"row_id":"row_001","source_label":"...","token":"c_solv_pentane","time_delta":0}, ...]}
  GET /api/clients
    -> {"clients":["160","197",...,"nexus_lab_solutions","retail_hardware_store","retail_supermarket"],"count":169,"model_version":"swiftron-onnx-v1"}
  GET /api/audit?limit=20
    -> {"tenant_id":"nexus_lab_solutions","events":[{"event_id":"...","tool_name":"predict_next_basket","status":"success","latency_ms":265, ...}],"count":N}
  ```
  status: pending

- [A to B] [15:00 2026-05-18]
  context: Lane A's Monday string-strip pass deliberately did not touch any file under `apps/web/` per lane ownership in AGENTS.md. Lane B owns dashboard cleanup.
  asks: Strip Northstar/Apex/NSI-VAL-100/mini-transformer references and hardcode `nexus_lab_solutions` where a single-tenant value is needed.
  contract: After the strip, `grep -rIn -e tenant_northstar -e tenant_apex -e Northstar -e Apex -e NSI-VAL-100 -e mini-transformer apps/web/` returns no hits.
  example: file `apps/web/src/lib/demo-data.ts` currently has hits on lines 14, 15, 19, 84, 227, 280, 285, 333. Replace tenant id with `nexus_lab_solutions`, drop the synthetic SKU rows, and replace `mini-transformer-v1` model_version strings with `swiftron-onnx-v1`.
  status: pending

- [A to C] [15:00 2026-05-18]
  context: Lane A's Monday string-strip pass deliberately did not touch `docs/demo-script.md` or any file under `services/mcp/tests/` per lane ownership in AGENTS.md. Lane A also deleted `services/mcp/erp_forecast/model.py`, `data.py`, and `jobs.py`, which `services/mcp/tests/test_core.py` still imports.
  asks: (1) Strip Northstar/Apex/NSI-VAL-100 references from `docs/demo-script.md` and rewrite the demo around `nexus_lab_solutions`. (2) Delete or rewrite `services/mcp/tests/test_core.py`; its imports `from erp_forecast.model import MiniTransformerForecaster` and the `tenant_northstar` test fixtures are dead.
  contract: After the strip, `grep -rIn -e tenant_northstar -e tenant_apex -e Northstar -e Apex -e NSI-VAL-100 -e mini-transformer -e MiniTransformer docs/ services/mcp/tests/` returns no hits, and `python3 -m unittest discover services/mcp/tests` either passes or has no tests left to run.
  example: in `docs/demo-script.md`, the opening line "Open the dashboard on `NSI-VAL-100`, segment `all`, 12 weeks" should become a single-client narrative against `nexus_lab_solutions` and the new locked tool surface (`predict_next_basket`, `predict_scenarios`, etc.).
  status: done

- [C to A] [16:12 2026-05-18]
  context: Lane C implemented the Python functions Lane A needs for the locked MCP tools.
  asks: Wire `predict_basket`, `run_beam`, `apply_sensor` plus `predict_with_session`, and `anonymize_and_tokenize` into the server tool layer.
  contract: function signatures match the pre-planned handoffs above.
  example: Lane A can import from `real_model.py`, `beam_search.py`, `sensor.py`, and `tokenize_orders.py`.
  status: done
