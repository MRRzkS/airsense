# Dashboard on Vercel

Vercel hosts the **dashboard only**. It cannot run the rest of this system: no
MQTT broker, no TimescaleDB, no Redis, and nothing that holds an open broker
subscription for the lifetime of the process. The backend lives on the VM in
[`oracle/RUNBOOK.md`](oracle/RUNBOOK.md).

## Setup

Copy `vercel.json` to `apps/dashboard/` (Vercel reads it from the project root),
then in the Vercel dashboard:

- **Root directory**: `apps/dashboard`
- **Environment variables**:

| Variable | Value |
| -------- | ----- |
| `VITE_API_URL` | `https://airsense.example.com/api` |
| `VITE_SIMULATOR_URL` | `https://airsense.example.com/sim` |

Both are read at **build** time — Vite inlines them into the bundle. Changing
either requires a redeploy, not just a restart.

## The part that will bite you

Set `PUBLIC_ORIGIN` on the VM to your **Vercel** URL, not the VM's own domain.
That value is what the two backend services accept as a CORS origin, and the
browser is calling them from Vercel. Getting this wrong produces a dashboard
that loads perfectly and then shows no data, with CORS errors only visible in
the browser console.

Preview deployments get their own generated origins, so they will be blocked
unless you add them too. For a portfolio demo, deploying only production is the
simpler path.
