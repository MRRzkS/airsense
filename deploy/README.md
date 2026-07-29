# Deployment

**None of this has been executed.** It is written from the documented behaviour
of the tools involved. Treat the first deploy as a debugging session.

| Path | What it is |
| ---- | ---------- |
| [`oracle/RUNBOOK.md`](oracle/RUNBOOK.md) | Step-by-step for an Oracle Cloud Always Free VM. The whole stack, behind Caddy for free TLS. |
| [`oracle/docker-compose.prod.yml`](oracle/docker-compose.prod.yml) | Overlay on the root compose file: no bind mounts, no reload, no published datastore ports. |
| [`oracle/Caddyfile`](oracle/Caddyfile) | `/api/*` and `/sim/*` reverse proxies, with SSE buffering disabled. |
| [`VERCEL.md`](VERCEL.md) + [`vercel.json`](vercel.json) | Dashboard only. Vercel cannot host the broker, the database, or a process holding an open MQTT subscription. |
| [`../.devcontainer/`](../.devcontainer/) | Codespaces, so a reviewer can boot the whole system in their own free quota without anyone hosting it. |

Free-tier terms move. Re-check Oracle's current Always Free shape allowances
before following the runbook — and note that a GCP `e2-micro` runs the same
compose file if they have changed.
