# Task Board

Single source of truth for what's shipped, in progress, and next per lane. Update on every meaningful commit. Agents read this before starting work.

## Status legend
- `[ ]` not started
- `[~]` in progress
- `[X]` done (meets Definition of Done in AGENTS.md)
- `[!]` blocked (see comms/blockers.md)

---

## Lane A — MCP server (Orkhan, Claude Code)

### Monday May 18
- [ ] Delete model.py, data.py, gut jobs.py, remove Northstar references
- [ ] Write CLAUDE.md as symlink to AGENTS.md
- [ ] Draft tool_schemas.py with all 6 tool signatures
- [ ] Mount artifacts/ in Dockerfile, set REAL_MODEL_ARTIFACT_DIR
- [ ] Drop OAuth PRM endpoint from server.py
- [ ] Update .env.example with new vars

### Tuesday May 19
- [X] Tool 1: predict_next_basket (wraps real_model.py from Lane C)
- [X] Tool 2: predict_scenarios (wraps real_model.py.run_beam from Lane C)
- [X] Audit log integration: every tool call recorded
- [X] (pulled forward) Tool 3: forecast_plan (adaptive strategy selection)
- [X] (pulled forward) Tool 4: personalize_client (wraps sensor.py from Lane C)
- [X] (pulled forward) Tool 5: anonymize_and_tokenize_orders (wraps tokenize_orders.py from Lane C)
- [X] (pulled forward) Tool 6: list_clients, list_audit_events
- [X] (pulled forward) Resources: swift://model-card, swift://dataset-card, swift://prediction/latest
- [X] (pulled forward) Prompt: procurement_planning_review
- Flix interview 12:00-14:30, async deliverables only

### Wednesday May 20
- [ ] MCP Inspector regression on all 6 tools end-to-end
- [ ] Confirm REST mirrors stay stable after Lane C merges sensor.py/tokenize_orders.py/beam_search.py to main

### Thursday May 21
- [ ] Coordinate merge to main with Lane B types.ts swap and Lane C tests

### Friday May 22
- [ ] Final smoke test
- [ ] Demo day

---

## Lane B — Dashboard (Maxat, Codex CLI)

### Monday May 18
- [ ] Strip Northstar references from demo-data.ts
- [ ] Strip NSI-VAL-100, tenant_northstar, tenant_apex everywhere
- [ ] Hardcode demo client picker to nexus_lab_solutions
- [ ] Confirm dashboard still loads with no console errors

### Tuesday May 19
- [ ] Basket sequence display panel (groups tokens by time delta)
- [ ] Scenario comparison panel (3+ beams side by side)
- [ ] Wire new MCP tools through REST mirror routes in apps/web/src/app/api/

### Wednesday May 20
- [ ] Sensor swap panel (before/after with visual diff)
- [ ] Anonymization audit panel (shows PII scrub + token mapping)
- [ ] Vercel preview deployment URL working

### Thursday May 21
- [ ] Vercel production deploy
- [ ] Polish: loading states, error states, empty states
- [ ] Mobile responsive check (judges may glance at phone)

### Friday May 22
- [ ] Demo day

---

## Lane C — Model + tests + demo (Sherniyaz, Codex CLI)

### Monday May 18
- [~] Clean real_model.py: lazy load ONNX session, lazy load SimulationDataset
- [!] Smoke test: call notebook inference path through real_model.py
- [~] Stub beam_search.py, sensor.py, tokenize_orders.py signatures
- [X] Pick the demo client and demo question, confirm with team

### Tuesday May 19
- [~] Implement beam_search.py: top-K-of-K trajectories, joint log-prob ranking
- [~] Verify beam search returns ranked outputs matching expected shapes from tool_schemas.py
- [~] First pass on tokenize_orders.py: raw CSV row to token sequence

### Wednesday May 20
- [~] Implement sensor.py: build sensor profile from product list, cache per session
- [~] Implement anonymize_and_tokenize_orders end-to-end (uses Lane A's privacy.py + tokenize_orders)
- [~] Pytest cases: prediction reproducibility, beam ranking, sensor swap behavior, anonymization round-trip
- [~] Demo script v1 in docs/demo-script.md

### Thursday May 21
- [ ] Demo script v2 after team dry-run
- [ ] Record fallback video (full 3-minute demo)
- [ ] Final tests pass

### Friday May 22
- [ ] Demo day

---

## Shipped (running log)

| Date | Lane | Item | Commit |
|------|------|------|--------|
| 2026-05-19 | A | tool_schemas.py + store.py + server.py scaffolding | beb1170 |
| 2026-05-19 | A | predict_next_basket + /api/predict | 8bf0467 |
| 2026-05-19 | A | predict_scenarios + /api/scenarios | 8e4844f |
| 2026-05-19 | A | forecast_plan + /api/forecast-plan | 9887b84 |
| 2026-05-19 | A | personalize_client + /api/personalize | 442f73a |
| 2026-05-19 | A | anonymize_and_tokenize_orders + /api/anonymize | a7b1a68 |
| 2026-05-19 | A | list_clients + list_audit_events + /api/clients + /api/audit | fdf331e |
| 2026-05-19 | A | swift:// resources + procurement_planning_review prompt | 0eb8ae1 |
