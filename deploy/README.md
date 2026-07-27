# Deployment

Populated in **P4**. Planned targets:

- `oracle/` — `docker-compose.prod.yml`, `Caddyfile` (free TLS) and a runbook
  for an Oracle Cloud **Always Free** Ampere VM. The stack deploys as the same
  compose file you run locally.
- `vercel.json` — the dashboard only. Vercel cannot host the broker, the
  database, or a process holding an open MQTT subscription, so the backend
  lives on the VM and the SPA points at it via `VITE_API_URL`.
- `../.devcontainer/` — a Codespaces badge so a reviewer can boot the whole
  system in their own free quota without us hosting anything.

Free-tier terms move. Re-check them before following the runbook.
