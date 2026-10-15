# TalentFlow

A multi-company hiring platform (applicant tracking system) built on Azure: companies run jobs,
pipelines, interviews and offers; candidates apply and track their applications through one
account.

- Specification: [specifications/SPECS.md](specifications/SPECS.md)
- Conventions and commands: [CLAUDE.md](CLAUDE.md)

## Prerequisites

- Docker Desktop (running)
- [uv](https://docs.astral.sh/uv/) — installs and pins Python 3.12 for the backend
- Node.js 24 LTS or newer, with npm

## Run locally

```sh
# 1. Local services (Postgres on host port 5433, Azurite)
docker compose up -d

# 2. Backend — http://localhost:8000
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run fastapi dev app/main.py

# 3. Frontend — open http://localhost:5173 (in a second terminal)
cd frontend
npm install
npm run dev
```

## Tests

```sh
cd backend && uv run pytest     # needs the Postgres container running
cd frontend && npm test
```
