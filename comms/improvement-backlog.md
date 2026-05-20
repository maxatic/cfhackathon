# Improvement Backlog — Red Team the MCP

The build is done and demo-ready. We have ~2 days of slack before Friday. This file is the queue for hardening and pushing the MCP further. Any AI session (Claude Code or Codex) picks an item from here, confirms it is unclaimed in `comms/task-board.md`, does it on its lane branch, and opens a PR.

## How to use this file

1. Pull main, read AGENTS.md, read this file.
2. Pick the highest-priority unclaimed item in your lane.
3. Mark it claimed: change `[ ]` to `[~LANE-X]` and commit that change first so other agents see it.
4. Do the work on your lane branch with the normal commit convention.
5. Each item has an acceptance test. Do not mark `[X]` until the acceptance test passes.
6. Open a PR. Note the item number in the PR body.

Rules from AGENTS.md still hold: do not modify `artifacts/*`, do not touch another lane's files, every tool call goes through the audit context, no AI buzzwords in user-facing text.

The standard for "improvement": every change must either make the demo more convincing, make the server harder to break during live Q&A, or close a gap a Swiftron ML judge would probe. If a change does none of those, skip it.

---

## Priority 1 — Things a judge will probe in Q&A

These are the most likely failure points if a Swiftron engineer pushes on the demo.

### [ ] P1-1 (Lane C) — Confirm beam search is real, not relabeled sampling
A judge will ask "is this actually beam search or top-k with a different name?" Read `real_model.py`'s `run_beam`. Confirm it (a) maintains multiple candidate sequences simultaneously, (b) expands each by the top tokens, (c) prunes to beam_width by cumulative log-prob, (d) the returned `joint_log_prob` is the actual sum of per-step log-probs, not a heuristic. If any of these is false, fix it so it is true. Write a test that proves a wider beam can surface a sequence that greedy top-1 would miss.
Acceptance: a Pytest case shows `run_beam(beam_width=4)` returns at least one trajectory whose first divergent token differs from the greedy argmax, and `joint_log_prob` values are monotonically non-increasing by rank and equal to the summed step log-probs within 1e-4.

### [ ] P1-2 (Lane C) — Make the sensor mechanism explainable in one sentence
The demo claims `personalize_client` shifts predictions via the model's sensor input. A judge will ask "what exactly does the sensor do to the model?" Read how `predict_basket(sensor_tokens=...)` feeds the ONNX `sensor_input`. Write a 5-line docstring at the top of `sensor.py` that states, truthfully, how additional_tokens become a sensor vector and why that changes the output distribution. No marketing words. If the honest answer is "it biases the sensor_input embedding toward those product tokens," say exactly that.
Acceptance: `sensor.py` module docstring explains the mechanism in plain language, and a Pytest case shows that two different token sets produce measurably different output distributions for the same client and seed.

### [ ] P1-3 (Lane A) — Harden every tool against bad input
During a live demo someone will type a nonexistent client, an empty token list, a negative beam_width, a huge max_generate. Every tool must return a clean, descriptive error, never a 500 stack trace. Audit-log the failure.
Acceptance: a Pytest or curl script hits each of the 7 tools with one malformed input and gets a 4xx with a readable message, and `list_audit_events` shows the failed call with status error.

### [ ] P1-4 (Lane A) — Latency budget under repeat calls
Demo will fire several tool calls in 3 minutes. Measure cold-start vs warm latency for each tool. If any warm call exceeds ~1.5s, investigate (model session re-init, dataset reload). The ONNX session and SimulationDataset should load once and stay cached.
Acceptance: a short benchmark script prints warm latency for all 7 tools; none exceeds 1.5s on Orkhan's Mac; document the numbers in `comms/lane-a-status.md`.

---

## Priority 2 — Make the demo more convincing

### [ ] P2-1 (Lane C) — Find the most dramatic sensor-swap demo pair
The personalization moment needs a visible shift. Sweep candidate `additional_tokens` sets and pick the one that produces the largest, most legible change in the predicted basket for `nexus_lab_solutions` (e.g. clearly pivoting from general chemistry to biology/PCR). Document the exact tokens to use in the demo.
Acceptance: `docs/demo-script.md` names the precise token list for the live personalization step, and a before/after example is recorded in the script.

### [ ] P2-2 (Lane C) — A second client for contrast
The demo is stronger if we can show the model behaves differently for a different client. Pick one numeric client whose vocabulary and predictions look clearly distinct from the chemistry lab (e.g. `retail_hardware_store` or `retail_supermarket` if they exist in the dataset). Document a one-line contrast we can show if a judge asks "does it just always predict lab supplies?"
Acceptance: `docs/demo-script.md` has a "contrast client" note with the client id and a sample prediction proving the model is client-specific, not a single global pattern.

### [ ] P2-3 (Lane B) — Dashboard copy reflects the vendor framing
Header still says "NexusLab procurement forecast." We pivoted to the vendor/supply-planner user. Update the header and subtitle to the vendor framing. Fix the status pill that says "Local fallback ready" even when connected to the live MCP; it should reflect real connection state.
Acceptance: header reads as a vendor-side B2B order forecast for the customer NexusLab; status pill shows live vs fallback truthfully; `npm run build:web` clean.

### [ ] P2-4 (Lane B) — Show the audit log live in the dashboard
The audit trail is a real differentiator ("this is a product, not an API"). Make sure the dashboard surfaces recent audit events with tool name, latency, and status, updating after each call.
Acceptance: clicking through Predict, Scenarios, Personalize visibly appends rows to the audit panel with real latencies.

---

## Priority 3 — Stretch features (only if P1 and P2 are done)

### [ ] P3-1 (Lane A) — A combined `procurement_brief` tool or prompt path
Right now an agent must chain calls. Consider a single high-level entry the agent can call that internally runs scenarios, picks the top, and returns a structured account-manager brief. This is exactly what Claude Desktop did manually in testing. Encoding it as a first-class prompt or tool makes the demo one step instead of three. Do NOT add it to the locked 6-tool surface; add it as an MCP prompt or a thin orchestration tool clearly marked as composite.
Acceptance: an MCP prompt or composite tool produces the account-manager brief in one call; demo script updated to show the one-call path as an option.

### [ ] P3-2 (Lane C) — Quantities or confidence in the output
The model returns tokens and timing. A judge may ask "how many units?" We cannot invent quantities, but we can expose per-token probability or a confidence band from the beam log-probs, which is honest. Surface normalized confidence per scenario (already shown in the Claude Desktop test as ~68/20/12 percent). Make that a real field in the `predict_scenarios` response.
Acceptance: `predict_scenarios` response includes a `relative_confidence` field per scenario derived from the joint log-probs (softmax over the returned beams), documented as relative-among-surfaced-beams, not absolute.

### [ ] P3-3 (Lane A) — Containerize for real
The brief mentions a containerized service. Get the Docker build working with the artifacts mounted as a volume (not copied into the image, to respect the NDA). This makes the "deployable product" claim concrete. Note the PyArmor Linux runtime is missing, so document that the container targets the platform whose runtime is present, or that the model mount is host-provided.
Acceptance: `docker compose up` boots the MCP server with the artifacts volume-mounted, `/healthz` responds, and at least one tool call succeeds through the container.

### [ ] P3-4 (Lane C) — Expand the test suite to the real model path
`test_core.py` exists but predates the real-model wiring. Add tests that exercise the real ONNX path end to end (gated on `REAL_MODEL_ARTIFACT_DIR` so they skip cleanly in CI without the bundle): predict reproducibility under fixed seed, beam ranking order, sensor swap effect, anonymization round-trip.
Acceptance: `python -m pytest services/mcp/tests` runs; real-model tests skip without the artifact dir and pass with it on Orkhan's Mac.

---

## Out of scope (do not build)

- OAuth, multi-tenant auth beyond the demo key
- Real model retraining (we expose sensor personalization, which is honest)
- Supabase persistence
- Any change to `artifacts/*`
- New tools on the locked surface beyond the composite prompt in P3-1

## Log
### 2026-05-20
- Backlog created after full build verified on main and validated end-to-end through Claude Desktop.
- All P1 items are judge-facing risk reduction. Do these first.
