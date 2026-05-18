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
- [ ] Tool 1: predict_next_basket (wraps real_model.py from Lane C)
- [ ] Tool 2: predict_scenarios (wraps beam_search.py from Lane C)
- [ ] Audit log integration: every tool call recorded
- Flix interview 12:00-14:30, async deliverables only

### Wednesday May 20
- [ ] Tool 3: forecast_plan (adaptive strategy selection)
- [ ] Tool 4: personalize_client (wraps sensor.py from Lane C)
- [ ] Resources: swift://model-card, swift://dataset-card

### Thursday May 21
- [ ] Tool 5: anonymize_and_tokenize_orders (wraps Lane C utilities)
- [ ] Tool 6: list_clients, list_audit_events
- [ ] Prompt: procurement_planning_review
- [ ] MCP Inspector regression test on all 6 tools

### Friday May 22
- [ ] Final smoke test
- [ ] Demo day

---

## Lane B — Dashboard (Maxat, Codex CLI)

### Monday May 18
- [X] Strip Northstar references from demo-data.ts
- [X] Strip NSI-VAL-100, tenant_northstar, tenant_apex everywhere
- [X] Hardcode demo client picker to nexus_lab_solutions
- [X] Confirm dashboard still loads with no console errors

### Tuesday May 19
- [X] Basket sequence display panel (groups tokens by time delta)
- [X] Scenario comparison panel (3+ beams side by side)
- [X] Wire new MCP tools through REST mirror routes in apps/web/src/app/api/

### Wednesday May 20
- [X] Sensor swap panel (before/after with visual diff)
- [X] Anonymization audit panel (shows PII scrub + token mapping)
- [X] Vercel preview deployment URL working

### Thursday May 21
- [ ] Vercel production deploy
- [X] Polish: loading states, error states, empty states
- [X] Mobile responsive check (judges may glance at phone)

### Friday May 22
- [ ] Demo day

---

## Lane C — Model + tests + demo (Sherniyaz, Codex CLI)

### Monday May 18
- [ ] Clean real_model.py: lazy load ONNX session, lazy load SimulationDataset
- [ ] Smoke test: call notebook inference path through real_model.py
- [ ] Stub beam_search.py, sensor.py, tokenize_orders.py signatures
- [ ] Pick the demo client and demo question, confirm with team

### Tuesday May 19
- [ ] Implement beam_search.py: top-K-of-K trajectories, joint log-prob ranking
- [ ] Verify beam search returns ranked outputs matching expected shapes from tool_schemas.py
- [ ] First pass on tokenize_orders.py: raw CSV row to token sequence

### Wednesday May 20
- [ ] Implement sensor.py: build sensor profile from product list, cache per session
- [ ] Implement anonymize_and_tokenize_orders end-to-end (uses Lane A's privacy.py + tokenize_orders)
- [ ] Pytest cases: prediction reproducibility, beam ranking, sensor swap behavior, anonymization round-trip
- [ ] Demo script v1 in docs/demo-script.md

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
| | | | |
