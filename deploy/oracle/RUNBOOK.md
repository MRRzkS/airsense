# Deploying to an Oracle Cloud Always Free VM

> **Check the terms before you start.** Free-tier allowances move, and this
> runbook was written against Oracle's Always Free tier as advertised in
> mid-2026. Confirm the current shape allowances and that your region has ARM
> capacity before committing to it. If Always Free has changed, a GCP `e2-micro`
> in `us-west1`/`us-central1`/`us-east1` runs the same compose file; the only
> difference is that 1 GB of RAM needs the tuning noted at the end.

Nothing in this runbook has been executed. It is written from the documented
behaviour of the tools involved — treat the first run as a debugging session,
not a formality.

## What you need

- An Oracle Cloud account (identity verification requires a card; Always Free
  resources do not charge it)
- A domain name, or a free subdomain from a dynamic-DNS provider
- An SSH key pair

## 1. Create the instance

Ampere A1 (ARM), 2 OCPU / 12 GB is comfortable and inside the usual Always Free
allowance. Ubuntu 24.04 LTS. If the console reports "out of host capacity", try
a different availability domain or region — this is common for ARM shapes.

Open ports 80 and 443 in the subnet's security list. Leave everything else shut:
the compose overlay publishes no other ports.

## 2. Point DNS at it

Create an `A` record for your domain to the instance's public IP. Caddy
provisions its TLS certificate from Let's Encrypt on first boot, which requires
the name to already resolve.

## 3. Install Docker

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER" && newgrp docker
```

Ubuntu's `iptables` rules on Oracle images block inbound traffic by default even
when the security list allows it:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 4. Configure

```bash
git clone <your-fork> airsense && cd airsense
cp .env.example .env
```

Edit `.env` and set, at minimum:

| Variable | Value |
| -------- | ----- |
| `POSTGRES_PASSWORD` | something that is not `airsense` |
| `AIRSENSE_DOMAIN` | `airsense.example.com` |
| `PUBLIC_ORIGIN` | `https://airsense.example.com` |

`PUBLIC_ORIGIN` is baked into the dashboard bundle at build time and is also
what the two backend services accept as a CORS origin. Changing it later means
rebuilding the dashboard image, not just restarting it.

## 5. Start

```bash
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.prod.yml run --rm ingest-api alembic upgrade head
```

The migration step is separate on purpose. Running migrations automatically on
container start means every replica races to apply them.

## 6. Verify

```bash
curl -s https://airsense.example.com/api/health
curl -s https://airsense.example.com/api/ready      # names any broken dependency
curl -s https://airsense.example.com/sim/devices
curl -sN https://airsense.example.com/api/stream | head -c 400   # should stream
```

The last one is the check worth doing: if it hangs with no output, Caddy is
buffering and `flush_interval -1` is not in effect.

## Putting the dashboard on Vercel instead

The compose file above serves the dashboard from the VM, which is the fewest
moving parts. To use Vercel instead, see [`../vercel.json`](../vercel.json) —
the backend deployment is unchanged, but `PUBLIC_ORIGIN` must then be the
**Vercel** URL so CORS allows it, while the dashboard's build-time
`VITE_API_URL` points at the VM.

## If you are on a 1 GB instance

TimescaleDB assumes more memory than a GCP `e2-micro` has. Add to the
`timescaledb` service:

```yaml
command: >
  postgres -c shared_buffers=128MB -c max_connections=25
           -c maintenance_work_mem=32MB -c effective_cache_size=384MB
```

and cap Redis with `--maxmemory 64mb --maxmemory-policy allkeys-lru`.

## Operating it

```bash
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.prod.yml logs -f ingest-api
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.prod.yml ps
```

Logs are JSON in production (`ENVIRONMENT=production`), so `| jq` works.

`/api/metrics` exposes Prometheus counters — `airsense_readings_ingested_total`,
`airsense_readings_rejected_total`, `airsense_tickets_opened_total`. There is no
Prometheus in this deployment; scraping it is left to whoever needs it.
