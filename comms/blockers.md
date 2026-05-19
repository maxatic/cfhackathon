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
