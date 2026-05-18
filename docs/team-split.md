# Team Split

## Person 1: MCP and Model Service

- Own `services/mcp`
- Keep tool contracts stable
- Verify Docker boot and MCP Inspector calls
- Prepare Railway/Render/Fly deployment

## Person 2: Dashboard and Deployment

- Own `apps/web`
- Wire Vercel env vars
- Keep dashboard readable on laptop and mobile widths
- Add Supabase-backed pages only if time remains

## Person 3: Data, Supabase, Demo

- Own `supabase` and `docs`
- Tune synthetic data and seed rows
- Validate RLS policies
- Run the demo script and record fallback video
