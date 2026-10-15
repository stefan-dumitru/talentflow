# CLAUDE.md

Durable conventions for this project. Auto-loaded into every session, so it stays short —
anything long or feature-specific belongs in [specifications/](specifications/SPECS.md), which is
read selectively.

Sections marked `[TODO]` are filled in per project. Everything else is a default that applies
unless this file says otherwise.

---

## Project

- **What this is:** TalentFlow, a multi-company hiring platform (applicant tracking system) on
  Azure: companies run jobs, pipelines, interviews and offers; candidates apply and track
  applications through one account. Portfolio project.
- **Full specification:** [specifications/SPECS.md](specifications/SPECS.md). Build phases are in
  [functional.md > Build Phases](specifications/functional.md#build-phases).

## Stack

- **Language / runtime:** Python 3.12 (backend, Functions); TypeScript
  (frontend).
- **Frontend:** React + TypeScript (Vite), shadcn/ui (on Radix UI) + Tailwind, MSAL for sign-in.
  Hosted on Azure Static Web Apps. Node 24 LTS or newer.
- **Backend:** FastAPI on Azure Container Apps; synchronous SQLAlchemy 2.0 (psycopg 3 driver,
  plain `def` endpoints) + Alembic; Pydantic. Background
  work: Azure Service Bus + Azure Functions (Python). PDFs: WeasyPrint.
- **Database:** Azure Database for PostgreSQL (Flexible Server); Postgres in Docker locally.
- **Azure services:** Entra External ID (auth), Blob Storage, AI Document Intelligence, Azure
  OpenAI + AI Search, SignalR Service, Communication Services (email), Key Vault + Managed
  Identity, Application Insights. Infrastructure: Bicep. CI/CD: GitHub Actions.
- **Testing:** backend — pytest + httpx against a real Postgres in Docker (never SQLite).
  Frontend — Vitest + Testing Library; Playwright for end-to-end flows.
- **Tooling:** uv (Python deps), Ruff (lint + format), mypy (types); npm and oxlint (lint) for the
  frontend; `openapi-typescript` + `openapi-fetch` for typed API calls (added in Phase 1).

## Commands

Backend commands run in `backend/`, frontend commands in `frontend/`. Rows marked *(not yet)*
don't exist until the phase named — tell me rather than inventing a workaround.

| Purpose | Command |
|---|---|
| Install dependencies | `uv sync` · `npm install` |
| Start local services | `docker compose up -d` (repo root). Postgres is on host port **5433** (5432 is taken by a Postgres installed on this machine). |
| Run in development | `uv run fastapi dev app/main.py` · `npm run dev` (open `http://localhost:5173`) · `func start` in `functions/` *(not yet, Phase 6)* |
| Run tests | `uv run pytest` (needs the Postgres container) · `npm test` · `npx playwright test` *(not yet, Phase 3)* |
| Run a single test file | `uv run pytest tests/path/test_x.py` · `npx vitest run src/path/x.test.tsx` |
| Lint / format | `uv run ruff check .` and `uv run ruff format .` · `npm run lint` (oxlint; no separate formatter yet) |
| Type check | `uv run mypy app` · `npm run typecheck` |
| Build for production | `npm run build` · API image: `docker build -t talentflow-api .` in `backend/` *(not yet, Phase 4)* |
| Database migration | `uv run alembic upgrade head` · new: `uv run alembic revision --autogenerate -m "..."` (a hook runs Ruff on each new file) |

Windows note: use `127.0.0.1`, not `localhost`, in database URLs — `localhost` tries IPv6 first
and adds a ~5 second delay per connection. The Vite dev server is the opposite: it listens on
`localhost`, so browse to `http://localhost:5173`.

## Project Structure

- `backend/` — FastAPI app. `app/api/` routers (thin), `app/services/` business rules,
  `app/models/` SQLAlchemy models, `app/schemas/` Pydantic, `app/core/` config, auth, tenancy,
  permissions, `app/integrations/` interfaces + real/fake clients for Azure services. `alembic/`,
  `tests/`.
- `functions/` — Azure Functions app (queue and timer handlers). Reuses `backend`'s models and
  services as a shared package [TODO — uv workspace or path dependency; decide in Phase 6].
- `frontend/` — React SPA. `src/features/<feature>/` per feature; `src/components/ui/` shadcn.
- `infra/` — Bicep templates. `.github/workflows/` — CI/CD.
- `specifications/` — the spec. `docker-compose.yml` — local Postgres, Azurite, Service Bus
  emulator.

---

## How We Work

My experience level: beginner-to-intermediate Python developer who enjoys building complex
fullstack apps; I've built a FastAPI + React multi-vendor marketplace before. Azure, TypeScript and
the Azure services here are newer to me — explain those parts more.

- **Plan before building.** For anything beyond a small edit, use Plan Mode first. Read the
  relevant `specifications/` file(s), propose an approach, and wait for my review before writing
  code.
- **Ask instead of assuming.** If a requirement is ambiguous and two readings would produce
  materially different code, ask. Don't guess and don't build both.
- **No new dependencies without asking first.** Name the library, what it's for, and what the
  alternative is without it.
- **Stay in scope.** Build what was asked. If you spot an unrelated problem, mention it — don't
  fix it in the same change.
- **Work in small, verifiable steps.** Prefer a working slice I can run over a large change I have
  to take on faith. For multi-step work, state the steps up front and stop at the end of each one.
- **Explain non-obvious decisions.** A one-line comment or a sentence in your reply. Not a tutorial
  on the obvious parts.
- **Keep specs in sync.** When a feature reveals a spec file is wrong or incomplete, update that
  file as part of the same work — not as cleanup later.
- **Report honestly.** If tests fail, show the output. If something is unverified, say so. "Done"
  means written, run, and checked.

## Definition of Done

A change is finished when all of these hold:

1. It does what was asked, and nothing extra.
2. It runs — verified by actually executing it, not by inspection.
3. Tests for the new behavior exist and pass, and the existing suite still passes. The exception
   is a spike or throwaway we've agreed is exploratory — say so out loud rather than quietly
   skipping this.
4. Lint / type check / format are clean.
5. Errors and empty states are handled, not just the happy path.
6. Any spec file the change contradicts has been updated.

## Code Style

- **Clear over clever.** Conventional, readable code beats a compact abstraction. If a junior dev
  would need to pause and work out what a line does, write the longer version.
- **Don't abstract early.** Duplication is cheaper than the wrong abstraction. Extract on the third
  use, not the first.
- **Match surrounding code.** Naming, file layout, and comment density should follow what's already
  in the file over any general preference here.
- **Name things for what they mean,** not what type they are. `unpaidInvoices`, not `dataArray`.
- **Handle errors where you can act on them.** No empty catch blocks, no swallowed failures.
- **Comment the why, not the what.** The code says what it does; comments explain why it's done
  that way.
- **Functions do one thing.** If you need "and" to describe it, it's two functions.
- **Store every timestamp in UTC,** regardless of where users are. Convert for display only.
  Mixing zones at the storage layer is nearly impossible to untangle later.
- **Project-specific conventions:**
  - Company-owned data is only ever queried through the central company scoping in
    `backend/app/core/tenancy.py` — never filter `company_id` by hand.
  - Routers stay thin: validation in Pydantic schemas, rules in `app/services/`, permission checks
    in `app/core/permissions.py`.
  - Side effects (email, PDFs, indexing, parsing) go through the outbox, never inline in a request.
  - Azure services are reached through `app/integrations/` interfaces so tests and local dev use
    fakes.

## Testing

- Write tests alongside the code, not as a later pass — the change isn't done until both exist.
  Where the expected behavior is already written down (the "Rules & edge cases" in a use case),
  write the test first.
- Derive a test from what the code *should* do, not from what it does. Reading a finished
  function and asserting its current output encodes the bug as the requirement.
- Cover the **behavior**, not the implementation — a test that breaks on every refactor is a
  liability.
- For each unit of logic: the expected case, the boundaries, and the failure case.
- Test what's genuinely yours. Don't write tests that only prove the framework works.
- A bug fix starts with a test that reproduces the bug and fails.
- Never weaken or skip a test to make a suite pass. A failing test is information — bring it to me.

## Security Baseline

Non-negotiable defaults for every project. App-specific requirements (auth model, compliance
scope, data sensitivity) live in [specifications/security.md](specifications/security.md).

- **Validate all input server-side,** at the boundary where it enters the system. Client-side
  validation is a convenience for the user, never a control.
- **Default-deny authorization.** Every endpoint requires an explicit check that this user may
  perform this action on this record. Absence of a rule means denied, not allowed.
- **No secrets in code** — no keys, passwords, tokens, or connection strings in source or in git.
  Environment variables or a secrets manager, and `.env` stays in `.gitignore`.
- **Parameterized queries only.** Never build SQL by string concatenation.
- **Hash passwords** with a strong, slow algorithm (bcrypt/argon2). Never store or log them in
  plaintext.
- **Escape user content on output** before it reaches HTML or the DOM.
- **Don't leak internals in error responses.** Generic message to the client, full detail to the
  server log.
- **Never log secrets or PII.**
- **HTTPS everywhere.** No credentials, tokens, or user data over plain HTTP, in any environment.
- **Never trust an uploaded filename.** Generate the stored path yourself; the original name is
  display metadata only. Authorize the upload *before* writing the file, not after.

## Git Conventions

- **Branch per change:** `feature/<short-name>`, `fix/<short-name>`
- **Commit messages:** imperative mood, subject under ~70 characters, explaining *why* in the body
  when the change isn't self-evident. e.g. `Add stock check before checkout`.
- **One logical change per commit.** Don't mix a refactor with a feature.
- **Never commit or push unless I ask.** Never force-push, never rewrite shared history, never
  commit directly to the default branch.
- **Never commit** secrets, `.env` files, build output, or dependency directories.
