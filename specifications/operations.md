# Operations & Runtime Requirements

The other spec files describe what the app *does*. This one describes how it behaves as a
*running system* — which is where most of "high-performance and scalable" actually lives.

Most of this file is gated. A local-only project or a prototype with no real users can answer
almost none of it and lose nothing; the same project once it's deployed and holding data someone
cares about needs most of it. The two ungated sections — **Concurrency & Write Correctness** and
**Query Efficiency** — apply the moment more than one person uses the app at once, and both are
far cheaper to decide now than to retrofit.

Fill in what you have real answers for. `[TODO]` is fine; a guessed number here is worse than a
blank, because it will get designed against.

## Availability & Recovery

> **Skip unless** someone other than you depends on this app being up, or it holds data that
> would genuinely hurt to lose.

- Uptime/availability target (e.g. "99.5%, business hours critical"): [TODO]
- Acceptable planned-maintenance downtime, and when it can happen: [TODO]
- Backup frequency, and how much data loss is tolerable (RPO): [TODO]
- How long a full restore may take (RTO), and whether a restore has ever actually been tested:
  [TODO — an untested backup is not a backup]

## Observability

- **Structured logging:** JSON logs from the API and Functions, sent to Application Insights via
  OpenTelemetry (Azure Monitor distro — new dependency, confirm in Phase 4). Every log line
  carries a request/correlation id, which also flows into Service Bus messages so a request and
  its background work can be traced together. No PII, CV text or tokens in logs.
- **Health checks:** `GET /health/live` — process is up (no dependencies checked).
  `GET /health/ready` — Postgres reachable. Container Apps probes use these.
- **Metrics:** [TODO — beyond App Insights defaults (request rate, failures, latency)].
- **Alerting:** messages arriving in a dead-letter queue raise an alert [TODO — to where: email?].
  Other alert conditions: [TODO].
- **Redaction:** request bodies are never logged. Query strings on file/SAS endpoints are stripped.
  Emails in log context are replaced by user ids.

## Environments & Configuration

- **Environments:** local and production. No staging in v1 (cost).
- **Runtimes:** Python 3.12 (pinned by uv), Node 24 LTS in CI and for the Static Web Apps build
  (local machines may run newer).
- **Local:** `docker-compose.yml` runs Postgres (host port 5433) and Azurite (Blob). Service Bus: the official
  Service Bus emulator in Docker [TODO — confirm it runs well on this machine; fallback is an
  in-process fake]. Document Intelligence, OpenAI, AI Search, SignalR and email are behind
  interfaces in `backend/app/integrations/` with fake implementations used locally and in tests,
  and real ones switched on by config.
- **Configuration:** `pydantic-settings` (`backend/app/core/config.py`) reads environment
  variables. Locally from `.env` (gitignored; `.env.example` committed with dummy values). In
  production, Container Apps secrets reference Key Vault, and services are reached with Managed
  Identity wherever Azure supports it, so most connections need no secret at all.
- **Release:** GitHub Actions on merge to `main`: lint + tests → build API image → push to a
  container registry [TODO — Azure Container Registry (small monthly cost) or GitHub Container
  Registry (free)] → `alembic upgrade head` → deploy a new Container Apps revision; frontend to
  Static Web Apps; Functions deployed from `functions/`; infrastructure from `infra/` (Bicep).
- **Rollback:** shift Container Apps traffic back to the previous revision. Migrations must stay
  backward-compatible with the previous revision for that to work (see below).
- **Cost guard:** an Azure budget alert on the subscription [TODO — amount]. Any resource with a
  meaningful monthly cost is flagged before it's provisioned.

## Database Migrations

The app isn't deployed with real data yet. **Until it is, dropping and rebuilding the database is
an accepted strategy.** Alembic is used from Phase 0 anyway, so the habit exists before it matters.

- Once production holds data you care about: zero-downtime expand/contract or a maintenance
  window? [TODO]
- Reversibility: every migration has a `downgrade` [TODO — enforce, or accept forward-only?].
- Large backfills: [TODO — not expected at demo scale].

## Background Jobs & Queues

- **Mechanism:** the API writes `outbox_messages` in the same transaction as the change; a
  dispatcher publishes them to Service Bus queues [TODO — dispatcher runs as a timer Function or
  an API background task; decide in Phase 6]. Azure Functions (Python) consume the queues. Timer
  Functions run scheduled work.
- **Queues / jobs:** `cv-parse`, `match-index`, `email`, `offer-pdf` [TODO — or sync], `gdpr`,
  `staff-import`. Timers: retention purge (nightly), scorecard reminders, outbox dispatch.
- **Retry policy:** Service Bus redelivery with max delivery count [TODO — number]; transient
  errors from Azure services retried in-handler with backoff first.
- **Permanently failed:** Service Bus dead-letter queue. The super-admin "Failed jobs" page lists
  dead-lettered messages (type, ids, error, time) with a **Retry** button that resubmits them.
  The record they belong to shows a failed state to its users (e.g. CV "parsing failed").
- **Delivery guarantee:** at-least-once. Every handler is idempotent: the outbox id is the Service
  Bus `message_id` (duplicate detection) and handlers check the target's state before acting
  (e.g. CV already `parsed` → no-op; email already sent for this outbox id → no-op).
- **Stuck/silent failure detection:** [TODO — e.g. `pending` outbox rows or `pending` CV parses
  older than N minutes surface on the Failed jobs page].
- **Suspended companies:** reminder timers skip them; candidate-triggered work (GDPR) still runs.

## External Integrations

| Service | If it's down | Surfaced to user? |
|---|---|---|
| Entra External ID | Nobody can sign in. Accepted. | Sign-in error page |
| Document Intelligence | Application is still submitted; parse retried, then `failed` | Recruiter sees parse status |
| Azure OpenAI + AI Search | Ranked view falls back to an unranked list | Banner on ranked view |
| Communication Services (email) | Queued and retried; the action that caused it still succeeds | No (failed sends → DLQ) |
| SignalR | Board works without live updates | "Live updates paused" indicator |
| Blob Storage | Uploads and downloads fail | Error on upload/download |

- **Timeouts and retries per integration:** [TODO — numbers]. Never an unbounded wait.
- **Circuit breaker:** [TODO — needed at demo scale?].

## Concurrency & Write Correctness

- **Simultaneous edits:** optimistic locking. Versioned tables (`jobs`, `applications`, `offers`,
  `interviews`, `companies`, `departments`, templates, `staff_members`) carry `version`; every
  update is `WHERE id = :id AND version = :expected`, and zero rows updated → **409 Conflict**.
  Clients send the version they loaded.
- **Idempotent operations:**
  - Apply: partial unique index (one active application per job) turns a double submit into a
    clean "already applied."
  - Queue handlers: outbox id (see Background Jobs).
  - Accept offer, approve/reject a step, submit scorecard: state-checked transitions (accepting
    an already-accepted offer is a no-op success).
  - [TODO — client-generated idempotency keys for bulk actions?]
- **Transaction boundaries (all-or-nothing):**
  - Any state change + its stage-history/audit row + its outbox messages.
  - Booking an interview slot: interview update + all participant rows.
  - Accepting an offer: offer `accepted` + application `hired` + job `hired_count` (+ auto-close).
  - Bulk board actions: one transaction **per application**, not one for the batch.
  - Staff import: one transaction per row.
  - Side effects outside the DB (email, PDF, indexing) never happen inside a request transaction —
    they go through the outbox, so "step 2 failed after step 1 committed" means a retried message,
    not an inconsistent record.
- **Known races:**
  - Two candidates' slot picks overlapping the same interviewer → Postgres exclusion constraint.
  - Two recruiters moving the same card → version check, 409, card refresh.
  - Last hire on a job: two offers accepted concurrently when one seat is left → lock the job row
    (`SELECT … FOR UPDATE`) in the accept transaction; the second gets "position filled."
  - Plan limits (publishing the N+1th job concurrently) → lock the company row when checking.
  - Two imports for the same company → [TODO, see `data-model.md`].

## Scalability Constraints

- **Statelessness:** the API holds no session, cache (except JWKS), or files locally. Identity is
  in the bearer token; files go straight to Blob; shared state is in Postgres; real-time fan-out
  goes through SignalR Service. Confirmed: the API can run multiple Container Apps replicas.
- **What breaks first:** [TODO — likely Postgres connections on the smallest tier, and free-tier
  limits on AI Search / SignalR].
- **Connection pool sizing:** [TODO — pool size × max replicas must stay under the Postgres tier's
  connection limit].

## Query Efficiency

- **N+1 prevention:** SQLAlchemy relationships default to `lazy="raise"`, so any un-planned lazy
  load fails loudly in tests. List endpoints load what they need explicitly with `selectinload` /
  `joinedload`.
- **No unbounded queries:** every list query has a `LIMIT`, internal ones included (batch jobs
  process in pages).
- **Query budget:** [TODO — e.g. max queries per list endpoint, asserted in tests].
- **Cache invalidation:** no application cache in v1, so nothing to invalidate.
