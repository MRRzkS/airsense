# airsense

> Predictive maintenance telemetry for internet-connected split air conditioner
> units. Connected units stream sensor readings; a model scores compressor
> degradation; when the score stays elevated, a support ticket opens in the CRM
> with the diagnostic code attached — before the customer notices anything is
> wrong.

**Status: P0 complete.** The shape is in place and CI is green. No telemetry
flows yet. See [docs/architecture.md](docs/architecture.md) for the phase table.

The demo GIF, the four domain rules, and the **Limitations and Honest Scope**
section land in P5. That last section is not optional: it will state which
dataset was used, what equipment it actually came from, and that the AC framing
is a domain mapping rather than proprietary appliance data.

---

## Quickstart

Requires Docker with Compose v2.

```bash
cp .env.example .env && make up
```

| Service | URL |
| ------- | --- |
| dashboard | http://localhost:3000 |
| ingest-api | http://localhost:8000/docs |
| device-simulator | http://localhost:8001/docs |
| metrics | http://localhost:8000/metrics |

`make` is not available on Windows by default. Every target is a thin wrapper,
so run the underlying command directly:

| Target | Equivalent |
| ------ | ---------- |
| `make up` | `docker compose up -d --build` |
| `make down` | `docker compose down` |
| `make logs` | `docker compose logs -f` |
| `make test` | `cd apps/ingest-api && pytest` |
| `make contracts` | `cd apps/ingest-api && lint-imports` |

## Layout

```
apps/ingest-api/       FastAPI. domain / application / infrastructure / api
apps/device-simulator/ replays a dataset to MQTT, injects faults on demand
apps/dashboard/        React + TypeScript + Vite operator console
ml/                    offline training and ONNX export (P2)
infra/                 broker and database configuration
deploy/                Oracle VM + Vercel deployment (P4)
docs/                  architecture and domain rules
```

## The dependency rule

```
api  ──▶  infrastructure  ──▶  application  ──▶  domain
```

`domain` imports nothing from the other layers and no third-party framework —
not even Pydantic. Two [import-linter](https://import-linter.readthedocs.io)
contracts in `apps/ingest-api/pyproject.toml` enforce this in CI:

```bash
cd apps/ingest-api && lint-imports
```

## Design

Palette and typography were chosen with the `ui-ux-pro-max` skill rather than
left at the shadcn default.

**IBM Plex Sans + IBM Plex Mono** — Plex was commissioned for an industrial
engineering company, its mono cut supplies tabular figures so live sensor values
do not jitter as digits change, and IBM Plex Sans JP exists should this ever
need a Japanese-language build.

**Control-room palette** — a cool near-black (`#0B0F14`) with three raised
surface steps, rather than stock shadcn slate. Device condition uses teal /
amber / red-orange, which stay distinguishable under the common forms of colour
blindness; every state is rendered with an icon and a label, never colour alone.
All foreground/background pairs clear WCAG AA, most clear AAA.

## What is deliberately not built

Authentication, multi-tenancy, a mobile app, Kubernetes manifests, a separate
model-serving service, energy analytics. Scoring runs in-process: a model
service is the right production answer and the wrong MVP answer, and the
tradeoff is written up in [docs/architecture.md](docs/architecture.md).
