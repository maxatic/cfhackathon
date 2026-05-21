# Lane A Status (Orkhan, Claude Code)

Update before each 10:00, 15:00, 19:00 standup. Latest entry on top. Four lines max:

```
### YYYY-MM-DD HH:MM
shipped: what got committed since last update
working: what's in progress now
next: what's next in queue
asks: what I need from other lanes (if anything, else "none")
```

---

### 2026-05-21 15:30
shipped: Step 0 red-team pass on Lane A surface (logged 6 bugs in blockers.md, none was a 500). P1-3 hardened every tool against bad input through a new validation.py with coercion helpers; type and bound checks now run inside the audit context, so failures the REST wrappers used to swallow (int/float casts) land in list_audit_events with status=error and a readable message. Trimmed the bad-client error so it no longer dumps all 169 client ids. P1-4 added services/mcp/scripts/bench_tools.py and ran it against the live server; ONNX session and SimulationDataset stay cached across calls.
working: opening PR from lane-a-server for review.
next: hand off to Orkhan for PR review; do not merge.
asks: none.

Warm latency table (services/mcp/scripts/bench_tools.py, one warm-up + 3 samples, REAL_MODEL on Orkhan's Mac, budget 1500ms):

```
tool                                   warm-up        p50        p95        max
--------------------------------------------------------------------------------
predict_next_basket                     144.5ms     137.2ms     140.9ms     140.9ms
predict_scenarios                       440.3ms     450.6ms     451.2ms     451.2ms
forecast_plan                           613.1ms     585.4ms     596.6ms     596.6ms
personalize_client                      100.3ms     102.0ms     102.2ms     102.2ms
anonymize_and_tokenize_orders             1.5ms       1.0ms       1.2ms       1.2ms
list_clients                              0.6ms       0.5ms       0.5ms       0.5ms
list_audit_events                         0.6ms       0.7ms       0.7ms       0.7ms
```

Every warm call is well under the 1.5s budget. Forecast_plan tops out at ~625ms because it currently routes to beam search on this objective; the per-call cost matches predict_scenarios + plan overhead, which is what we want.

### 2026-05-19 10:00
shipped: nothing yet today, Monday work pushed last night to lane-a-server.
working: drafting tool_schemas.py + store.py + scaffolding server.py for the 6 locked tools per handoffs 1-5. Will wire predict_next_basket and predict_scenarios first since Lane C's real_model.py is validated on this Mac.
next: forecast_plan adaptive routing, personalize_client wrapping Lane C's sensor.py, anonymize_and_tokenize_orders wrapping Lane C's tokenize_orders.py, list_clients, list_audit_events, swift://* resources, procurement_planning_review prompt. Will smoke-test every REST route with curl before each commit.
asks: Maxat — handoff posted in handoffs.md with the new TypeScript types I added to types.ts (additively, no deletions). Update mcp-client.ts to call /api/predict, /api/scenarios, /api/forecast-plan, /api/personalize, /api/anonymize, /api/audit, /api/clients when you're ready. Sherniyaz — Lane C wrappers behaved correctly under real ONNX inference; no changes needed from you for the wire-up itself.

### 2026-05-19 11:50
shipped: all 6 locked MCP tools + REST mirrors + 3 swift:// resources + procurement_planning_review prompt on lane-a-server (9 commits, beb1170..0eb8ae1). Smoke-tested every REST endpoint against the real Swiftron bundle on my Mac: /api/clients returns 169 clients, /api/predict generates 6 tokens with correct dt_2w time delta, /api/scenarios returns 3 ranked beams with descending joint_log_prob, /api/forecast-plan routes to beam vs top_k from objective_text keywords, /api/personalize swaps sensor and produces sensor_profile strategy, /api/anonymize hashes customer_name+email and scrubs ship_to_address, /api/audit shows all 8 success events plus 1 error event from the bad-payload path. Error paths return 400 with a clear message.
working: nothing, blocked on Flix interview from 12:00-14:30.
next: at 15:00 standup, push lane-a-server to origin and ping the team. Hold off on PR to main until Sherniyaz confirms Lane C's beam_search.py / sensor.py / tokenize_orders.py are merge-ready and Maxat confirms types.ts swap.
asks: Maxat — when you wire mcp-client.ts, drop `process.env.MCP_DEMO_TOKEN ?? "sk_northstar_forecast_full"` to just `process.env.MCP_DEMO_TOKEN` (the northstar fallback is dead). Sherniyaz — Tuesday morning Pytest cases in services/mcp/tests/ should cover the 6 tools, not the deleted MiniTransformerForecaster.

### 2026-05-18 19:00
shipped: nothing since 15:00, Lane A Monday tasks complete on lane-a-server (8 commits)
working: nothing, Monday work done
next: Tuesday 09:30 merge dance (Lane A to main first to lock deletions, then B and C rebase), then wire Lane C's predict_basket / run_beam / sensor / anonymize_and_tokenize into the 6 locked MCP tools per handoffs 1-5
asks: Sherniyaz — send me your failing PyArmor smoke test code in Telegram, I'll run real-inference on my Mac since my system doesn't have the macOS code-signature block

### 2026-05-18 15:00
shipped: branch lane-a-server with 8 commits — deleted model.py/data.py/jobs.py, extracted audit.py, stripped Northstar/Apex/NSI-VAL-100/mini-transformer from Lane A + shared files, dropped OAuth PRM + WWW-Authenticate, gutted orphaned server.py tools/resources/routes, updated .env.example with REAL_MODEL_ARTIFACT_DIR, symlinked CLAUDE.md → AGENTS.md.
working: server.py is back to a minimal importable shell (erp_real_sequence_forecast + demand_planning_review + healthz + /api/real-sequence + BearerAuth middleware) ready for the locked tool surface rebuild starting Tuesday.
next: Tuesday morning draft tool_schemas.py with all 6 locked tool signatures, then wire predict_next_basket and predict_scenarios behind Lane C's `predict_basket` and `run_beam` from handoffs 1 + 2.
asks: Maxat — please strip Northstar/Apex/NSI-VAL-100/mini-transformer from apps/web/src/lib/demo-data.ts (handoff A→B posted, your demo-data.ts has 8 hits). Sherniyaz — please clean docs/demo-script.md and delete or rewrite services/mcp/tests/test_core.py which still imports the deleted MiniTransformerForecaster (handoff A→C posted). Not merging to main; rebase off main when we sync.
