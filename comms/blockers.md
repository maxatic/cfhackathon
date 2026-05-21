# Blockers

Anything that needs another lane's help. Format:

```
- [LANE-X] [HH:MM YYYY-MM-DD] one-line blocker description
  resolved-by: [LANE-Y] [HH:MM YYYY-MM-DD] resolution note
```

Rule: if you are stuck for more than 45 minutes, post here and ping the other lane in team chat.

---

- [LANE-B] [15:50 2026-05-18] Vercel preview deploy is blocked: repo is not linked locally, no Vercel CLI is installed, and the connected Vercel project appears to target a different GitHub repo named `hackathon`
  resolved-by: [LANE-B] [18:55 2026-05-18] branch preview verified at https://cf-hackathon-dashboard-jd5c7nc4z-maxatics-projects.vercel.app/
- [LANE-B] [16:02 2026-05-18] Preview URL https://cf-hackathon-dashboard.vercel.app/ is reachable but serves the old Northstar dashboard, not `lane-b-dashboard`
  resolved-by: [LANE-B] [18:55 2026-05-18] correct branch URL verified at https://cf-hackathon-dashboard-jd5c7nc4z-maxatics-projects.vercel.app/

- [LANE-A] [15:00 2026-05-21] Step 0 red-team pass on Lane A surface found six real bugs across the REST tool wrappers. None is a 500, but every one would surface as wrong output or a missing audit trail under a judge probe. Fixing under P1-3.
  1. `/api/predict` and `/api/personalize` silently coerce a string `start_sequence` / `additional_tokens` into a list of characters because the REST wrapper passes the raw value through and Python iterates the string. Returns 200 with garbage tokens; not caught anywhere.
  2. Same endpoints accept non-string list elements (e.g. `[1,2,3]`) without complaint; integers reach the model wrapper and run.
  3. REST wrappers `int(body.get(...))` casts on `max_generate`, `top_k`, `temperature`, `seed`, `beam_width`, `horizon`, `horizon_hint`, and `limit` raise `ValueError` BEFORE the `_AuditContext` is entered, so the failed call is NEVER recorded in the audit log. AGENTS.md requires every tool call to land in audit.
  4. Bad-client errors dump all 169 client ids into the error string. Recoverable advice should be terse; the agent can call `list_clients`.
  5. `/api/anonymize` with a non-dict row element returns a raw Python type error: `'int' object is not iterable`. Not agent-recoverable.
  6. No upper bound on list lengths. 50,000-row `raw_rows` payloads are accepted and processed. No DoS guard at the wire boundary.
  resolved-by: [LANE-A] [HH:MM 2026-05-21] under P1-3.
