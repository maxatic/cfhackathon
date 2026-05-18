# AGENTS.md — Swiftron MCP Hackathon Repo

You are working inside a three-person hackathon team building an MCP server that wraps Swiftron's pretrained ONNX forecasting model. This file is the canonical context every agent in this repo reads. Both Claude Code and Codex CLI read it. Do not duplicate rules into CLAUDE.md; that file symlinks here.

Read this entire file at session start. Re-read after pulling from main.

## What we are building

A containerized MCP server that exposes Swiftron's pretrained B2B order-prediction model to AI agents over the Model Context Protocol. Tools accept a client id and parameters, run inference through Swiftron's `SimulationDataset` interface, return predicted order baskets. Dashboard visualizes the same data for the demo.

Demo on Friday May 22, 2026 at the CF x HHN AI Hackathon in Heilbronn.

## Source of truth (untouchable)

These files come from Swiftron under NDA. Do not modify, decrypt, inspect, or bypass them. They live OUTSIDE git at `artifacts/` (gitignored). Each team member unzips Swiftron's bundle to their own `artifacts/` folder and sets `REAL_MODEL_ARTIFACT_DIR` in `.env`.

Bundle contents:
- `landing_page_model.onnx` — pretrained transformer
- `multi_client_dataset.joblib` — 169 clients with anonymized vocab
- `alit_backend.py` — PyArmor-protected interface
- `pyarmor_runtime_*/` — protected runtime
- `hackathon_inference.ipynb` — reference inference notebook

Call them through `SimulationDataset` only. If a function feels like it needs to reach inside the protected code, the answer is no.

NEVER commit any file from `artifacts/` to git. NEVER copy the contents of `multi_client_dataset.joblib` into any source file. NEVER include Swiftron's actual vocabulary in commit messages, comments, or docs visible in the public repo.

## Repo structure (target state after Monday cleanup)

```
artifacts/                        # NDA bundle, GITIGNORED, mounted via env var
services/mcp/erp_forecast/
  server.py                       # FastMCP + Starlette REST dual surface
  auth.py                         # one demo tenant, scoped API key
  audit.py                        # extracted audit context manager
  store.py                        # thin orchestrator
  real_model.py                   # wraps SimulationDataset + ONNX session
  beam_search.py                  # NEW: real beam over decoder
  sensor.py                       # NEW: sensor-based personalization
  tokenize_orders.py              # NEW: raw orders to token vocab
  privacy.py                      # PII scrub, kept as-is
  tool_schemas.py                 # MCP tool input/output schemas
  tests/
apps/web/                         # Next.js 16 dashboard, NexusLab themed
docs/
  demo-script.md                  # 3-minute narrative
comms/                            # AI-to-AI coordination (see below)
  task-board.md
  blockers.md
  handoffs.md
  lane-a-status.md
  lane-b-status.md
  lane-c-status.md
AGENTS.md                         # this file (canonical)
CLAUDE.md                         # symlink to AGENTS.md
```

What gets deleted Monday morning: `services/mcp/erp_forecast/model.py` (fake transformer), `data.py` (synthetic ERP generator), most of `jobs.py` (synthetic store), all Northstar/Apex/NSI-VAL-100 references, OAuth PRM endpoint, fake retraining state machine, `supabase/seed.sql` Northstar rows.

## MCP tool surface (locked, do not redesign)

Six tools, three resources, one prompt. Names are final. Schemas live in `services/mcp/erp_forecast/tool_schemas.py`.

| Tool | Owner | What it does |
|------|-------|--------------|
| `predict_next_basket` | A wraps C | Autoregressive prediction, top-K sampling with uniqueness |
| `predict_scenarios` | A wraps C | Real beam search, K ranked trajectories with joint log-prob |
| `forecast_plan` | A | Adaptive: agent passes intent text, server picks decoder strategy |
| `personalize_client` | A wraps C | Builds sensor profile, runs prediction with it |
| `anonymize_and_tokenize_orders` | A wraps C | PII scrub then map to Swiftron vocab |
| `list_clients` | A | Meta |
| `list_audit_events` | A | Meta |

Resources: `swift://model-card`, `swift://dataset-card`, `swift://prediction/latest`.
Prompt: `procurement_planning_review`.

## Lane ownership (no file collisions)

| Lane | Owner | AI tool | Files owned exclusively |
|------|-------|---------|------------------------|
| A. MCP server | Orkhan | Claude Code | `services/mcp/erp_forecast/server.py`, `auth.py`, `audit.py`, `store.py`, `tool_schemas.py`, `Dockerfile`, `pyproject.toml`, `.env.example`, `AGENTS.md`, `CLAUDE.md` |
| B. Dashboard | Maxat | Codex CLI | Everything under `apps/web/`, `vercel.json` |
| C. Model + tests + demo | Sherniyaz | Codex CLI | `services/mcp/erp_forecast/real_model.py`, `beam_search.py`, `sensor.py`, `tokenize_orders.py`, `privacy.py`, all `services/mcp/tests/`, `docs/demo-script.md` |

Rule: no file is touched by two lanes. Cross-lane work goes through `comms/handoffs.md`.

**Lane C runs on Codex with a vibe-coding owner.** This means contracts coming from Lane A into Lane C must be unambiguous: exact function signatures, exact return shapes, at least one example input/output. Lane A reviews Lane C PRs lightly before they merge to main. If Lane C is stuck for 45 minutes, Lane A pairs.

## Coding rules

- Python 3.11+. Type hints on every public function. Type errors fail CI.
- No bare `except:`. Always raise descriptive errors with the context an agent can use to recover.
- No `print()` in stdio MCP servers. It corrupts JSON-RPC. Log to stderr only.
- Every tool call goes through `audit.py`. Latency, identity, status, error summary recorded.
- No silent fallbacks to synthetic data in production code paths. Either call the real model or raise.
- No commented-out code. Delete it or it stays out.
- Test the public interface, not the implementation. Tests that mock everything are useless.
- New file includes a one-line module docstring.
- For Lane C (vibe-coded with Codex): every function gets a docstring with example input/output. This is mandatory, not optional. Codex generates better code from explicit examples.

## Style and voice rules for any user-facing text (docs, demo script, dashboard copy)

- No em dashes anywhere. Use commas, colons, or sentence breaks.
- No AI buzzwords: leverage, robust, delve, comprehensive, navigate, intricate, tapestry, journey, unleash, seamless, holistic.
- No hedge phrases without commitment ("it depends" with no follow-through).
- Direct sentences. Active voice. Short over long.
- Numbers must be provable from the dataset or the model.

## Bundle distribution

Each team member receives the NDA bundle ZIP from Orkhan via Telegram on Sunday night. Unzip to `<repo-root>/artifacts/`. Set in your `.env`:

```
REAL_MODEL_ARTIFACT_DIR=/Users/<your-name>/Documents/cfhackathon/artifacts
```

The `artifacts/` folder is gitignored by `.gitignore` via patterns `*.onnx`, `*.joblib`, `pyarmor_runtime_000000/`. Verify with `git status` that the unzipped files do not appear in the staging area. If they do, fix `.gitignore` before doing anything else.

## Commands

```bash
# Run MCP service (Lane A)
cd services/mcp
source .venv/bin/activate
uvicorn erp_forecast.server:app --reload --port 8000

# Run dashboard (Lane B)
npm run dev:web   # from repo root, runs on :3000

# Run MCP Inspector against the service (Lane A or C)
npx @modelcontextprotocol/inspector \
  --url http://localhost:8000/mcp

# Run tests (Lane C, mandatory before merging to main)
npm run test:mcp

# Health check
curl http://localhost:8000/healthz
```

## Sync cadence and comms

Three standups per day: 10:00, 15:00, 19:00. Each lane owner writes a four-line update in their `comms/lane-X-status.md` file before each standup, then pings the team Telegram with "lane-X update posted." The other two read it before posting their own.

Blockers go in `comms/blockers.md` with the format:
```
- [LANE-X] [HH:MM] one-line blocker description
  resolved-by: [LANE-Y] [HH:MM]
```

Cross-lane handoffs go in `comms/handoffs.md` with the format:
```
- [from-LANE to-LANE] [HH:MM]
  context: what was done
  asks: what the other lane needs to do
  contract: exact function signature and return type
  example: one concrete input and output
  status: pending | accepted | done
```

The `comms/task-board.md` is the source of truth for what's shipped, what's in progress, what's next per lane. Update on every meaningful commit.

## Commit message convention

All commits to lane branches and main must follow:
```
[LANE-X][TOOL_OR_AREA] short imperative description

optional body for context, breaking changes, or why
```

Examples:
- `[LANE-A][server] add forecast_plan tool stub`
- `[LANE-B][dashboard] strip Northstar references from demo-data`
- `[LANE-C][beam_search] return ranked trajectories with joint log-prob`

This lets every lane see what the others touched in one `git log --oneline`.

## Branch strategy

- `main` is always demoable. Anything broken on main blocks the demo.
- Each lane works on its own branch: `lane-a-server`, `lane-b-dashboard`, `lane-c-model`.
- PRs to main require one other person to skim. Five minutes max.
- Daily merge cutoff at 22:00. Nothing merged after that without team agreement.

## Definition of done per tool

A tool is "done" only when all four conditions hold:

1. Implemented and committed on its lane branch
2. Tested via MCP Inspector with at least one happy path and one error path
3. At least one Pytest case exists in `services/mcp/tests/`
4. Dashboard panel calling it works (Lane B confirms)

Anything short of all four stays "in progress" on `comms/task-board.md`.

## Demo voice (for `docs/demo-script.md`)

Speak to procurement managers, not engineers. The hero is the customer (NexusLab Solutions, a chemistry research lab). The model is the tool. The MCP is invisible plumbing the customer never sees. Lead with the question the customer would ask, then show the agent answering it.

## What never to do

- Modify `artifacts/*`. They are Swiftron's NDA-protected source of truth.
- Commit anything in `artifacts/` to git.
- Paste Swiftron's actual vocabulary, real client names beyond `nexus_lab_solutions`, or model card text into the public repo.
- Add new top-level dependencies without telling Lane A. The Docker image build time matters.
- Use synthetic data anywhere outside the dashboard's offline fallback.
- Push to main directly without a PR.
- Implement features outside your lane without asking the lane owner.
- Implement features not on the locked tool surface above.
- Re-add OAuth PRM, fake retraining, or multi-tenant scope.

## Standing rules for the week

- 09:30 Monday at Gravity Heilbronn campus.
- Tuesday 12:00-14:30 Orkhan is in a Flix interview. Quiet room booked. Lane B and C continue independently.
- Demo Friday morning. Friday is recovery + rehearsal, no new features after Thursday 18:00.
- If anyone is stuck for 45+ minutes, post in `comms/blockers.md` and pair-up to unblock.
- Team Telegram for "I'm here" / "standup posted" pings. No code coordination over Telegram. All code coordination lives in this repo.
