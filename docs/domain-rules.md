# The four domain rules

Most predictive-maintenance demos fire a ticket the instant a score crosses a
threshold. That is a demo, not a system: it produces flapping states, duplicate
tickets, severity that means nothing, and a CRM full of churn for one broken
compressor.

These four rules are the difference. They live in `apps/ingest-api/src/airsense/domain/`,
import nothing but the standard library, and carry **77 tests** between them.

All thresholds below are defaults from `infrastructure/config.py` and are
overridable by environment variable. The rules themselves take them as
arguments, so tests exercise values the test chooses.

---

## 1. Hysteresis and debounce

`domain/conditions.py` · `ConditionPolicy`

A degradation score is noisy. Two mechanisms, both required:

**Debounce** — a transition needs `sustained_samples` (default 5) consecutive
readings past the threshold. One spike changes nothing.

**Hysteresis** — the score must fall *meaningfully* below the entry threshold
before the state relaxes, not merely back across it. Entry and exit thresholds
are separated by a 0.10 deadband:

| Transition | Enter | Exit |
| ---------- | ----- | ---- |
| NORMAL → WATCH | 0.50 | 0.40 |
| → ALERT | 0.75 | 0.65 |

Debounce alone is not enough. A score oscillating around a single value
satisfies a debounce window in *both* directions and flaps anyway; the deadband
is what stops it. There is a test for exactly this — twenty samples alternating
either side of `watch_enter` produce **zero** transitions.

**Escalation is fast, de-escalation is slow.** A rapidly degrading unit may jump
NORMAL → ALERT in one transition, but recovery always steps back one level at a
time. Being late to stand down is cheap; being late to raise an alarm is the
failure this system exists to prevent.

## 2. Ticket deduplication

`domain/ticketing.py` · `TicketPolicy`

At most one open ticket per `(device, fault class)`. A device that keeps
alerting updates the existing ticket's severity; it never opens a second.

Severity **ratchets** while a ticket is open — it can rise, never fall. A
technician dispatched against a HIGH ticket should not find it quietly
downgraded because the unit had a good hour.

## 3. Severity mapping and escalation

`domain/severity.py` · `SeverityPolicy`

Severity is a function of two things, not one: *where* the score sits and *how
fast it is moving*.

| Band | Severity |
| ---- | -------- |
| < 0.60 | LOW |
| ≥ 0.60 | MEDIUM |
| ≥ 0.75 | HIGH |
| ≥ 0.90 | CRITICAL |

A device climbing faster than `fast_degradation_per_sample` (default 0.008
health index per sample) is promoted **one level**. A unit parked at 0.62 for a
week and a unit that reached 0.62 this morning need different responses, and a
band-only mapping cannot tell them apart.

Rate of change never *demotes*: bad but stable is still bad. A single sample has
a rate of zero by definition — one reading is a position, not a trend, and
inventing a slope from it would let a spike promote a device.

## 4. Cooldown

`domain/ticketing.py` · `TicketPolicy.cooldown`

Once a ticket closes, the same fault class cannot re-open for a quiet period
(default 30 minutes). Without it, a unit sitting on the threshold closes and
re-opens a ticket on every oscillation, and the CRM fills with churn that looks
like many faults instead of one unresolved one.

A ticket is resolved when the device returns to **NORMAL** — not to WATCH.
Closing on the way down would re-open it on the next wobble, which is precisely
what the cooldown exists to catch. Better not to close at all.

---

## How they compose

```
score ──▶ ConditionPolicy ──▶ condition ──┐
              (rule 1)                    │
                                          ▼
recent scores ──▶ SeverityPolicy ──▶ TicketPolicy ──▶ action
                     (rule 3)         (rules 2, 4)
                                                       │
                                    OPEN / ESCALATE / RESOLVE / SUPPRESS / HOLD
                                                       │
                                                       ▼
                                                  TicketSink
```

`application/use_cases/assess_degradation.py` orchestrates them and talks to the
ports. It contains no thresholds and no branching on score values — every
decision comes from the domain.
