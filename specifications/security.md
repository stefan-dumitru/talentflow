# Security Requirements

The project-wide default posture (validate input, no secrets in code, default-deny authz) is in
[../CLAUDE.md](../CLAUDE.md) and applies regardless of what's filled in below. This file is for
requirements specific to *this app* — its data sensitivity, its auth model, its compliance scope.

## Data Sensitivity

- **Most sensitive data:** candidate PII — names, contact details, CVs (work history, education,
  and whatever else candidates put in them, which can include photos, age or other special
  categories), interview feedback, and salary/offer details.
- **Regulatory scope:** GDPR-aware by design (data export, deletion via anonymization, per-company
  retention). It's a portfolio project, so there's no formal compliance certification.

## Authentication

- **Method:** Microsoft Entra External ID for everyone. The SPA signs in with MSAL
  (authorization code + PKCE) and sends an access token as `Authorization: Bearer` to the API.
- **API token validation** (`backend/app/core/auth.py`): signature against External ID's JWKS
  (cached), `iss`, `aud` (the API's app registration), `exp`/`nbf`. Anything else → 401.
- **Session handling:** no server sessions or cookies on the API. Token lifetimes are External ID
  defaults [TODO — confirm]; MSAL renews silently. Token cache location in the browser: MSAL
  default (`sessionStorage`) [TODO — confirm].
- **MFA:** required for staff (enforced through External ID policy/conditional access for staff
  accounts), optional for candidates. How staff are targeted by the policy (group, app role):
  [TODO — decide in Phase 1].
- **Identity found in External ID but not in TalentFlow:**
  - No `users` row → created as a candidate on first sign-in. Never granted staff access.
  - A login is staff or candidate, never both (see `functional.md` > Authentication).
  - `users` row with a pre-created staff record matching the email and no `external_id` yet →
    linked on first sign-in. Email must be verified by External ID.
  - Staff record exists but `is_active = false` → "account disabled" page; every staff endpoint
    returns 403. Fails closed.
  - Company suspended → staff can read but every write returns 403 with the suspension message.
  - `is_platform_admin` is only ever set by a CLI/seed command, never through the API.

## Authorization

- **Model:** role-based (roles from `functional.md` > User Roles) **plus** record-level scope
  (company, job assignment, hiring-manager ownership, interview participation, candidate
  ownership).
- **Enforcement pattern:**
  - `get_principal` FastAPI dependency (`backend/app/core/auth.py`) resolves the token to a
    `Principal`: `user_id`, `company_id | None`, `roles`, `is_platform_admin`, `is_candidate`.
  - `require_roles(...)` dependency on every staff route; routers default to deny (a route without
    an explicit dependency fails a test that walks all routes).
  - **Company scoping** in one place (`backend/app/core/tenancy.py`): every query on a
    company-owned model is filtered to `principal.company_id` automatically, using a SQLAlchemy
    `do_orm_execute` event that applies `with_loader_criteria` to every company-owned model. Not
    Postgres Row-Level Security (decision: easier to read and debug; protection lives in the
    app). Cross-company access is tested explicitly.
  - Record-level checks in `backend/app/core/permissions.py` (e.g. `can_act_on_job`,
    `can_view_scorecards`) called from services, never inline in routers.
  - Records outside the user's scope return **404**, not 403, so IDs can't be probed.
  - Super-admin endpoints live under `/platform/*` and can't reach company hiring data at all.

## Data Protection

- **Encryption at rest:** Azure platform default for PostgreSQL and Blob Storage
  (service-managed keys). Column-level encryption: [TODO — none planned; salary is the candidate].
- **Transit beyond HTTPS:** [TODO — public endpoints with firewall rules, or VNet + private
  endpoints for Postgres/Storage (adds cost)].
- **Extra-protected fields:** CV files and text, candidate contact fields, scorecards, offer
  salary — never logged, never in queue payloads (messages carry ids only), never in the audit
  log's `changes` (except salary, which is company data).
- **Blob access:** containers are private. The API hands out read-only SAS URLs, scoped to one
  blob, valid for 10 minutes. The API itself reaches Storage via Managed Identity, not
  account keys.

## File Upload Handling

The two baseline rules from CLAUDE.md apply (app-generated stored path; authorize before writing).

- **Allowed types and size:**
  - CVs: PDF and DOCX, max 5 MB. Checked by content (magic bytes), not just extension or
    `Content-Type`.
  - Company logos: PNG, JPEG, WebP (no SVG — it can carry script), max 1 MB.
  - Staff import: CSV, max 1,000 rows.
- **Storage and naming:** Azure Blob Storage, private containers: `cvs/<user_id>/<uuid>.<ext>`,
  `offers/<company_id>/<offer_id>/<uuid>.pdf`, `logos/<company_id>/<uuid>.<ext>`,
  `exports/<user_id>/<uuid>.json`. Uploads stream to Blob; nothing is written to the container's
  local disk.
- **DB stores:** the blob name (relative to its container), never a full URL.
- **Original filename:** kept in `cv_documents.original_filename` for display only (escaped on
  output).
- **Malware scanning:** none in v1 (Microsoft Defender for Storage costs money) — accepted risk,
  see Threat Model.

## Threat Model (lightweight)

- **Biggest realistic threats:**
  1. Cross-company data leak (one company reading another's candidates by changing an ID) —
     mitigated by central company scoping + 404s + explicit isolation tests.
  2. Candidate PII exposure (to the wrong role, in logs, through a long-lived file link) —
     mitigated by role/record checks, log redaction, short-lived SAS.
  3. Malicious uploads (disguised executables, DOCX macros, oversized files) — content-type
     sniffing, size limits, files never executed or rendered server-side except by Document
     Intelligence.
  4. Template injection via company-edited email templates — fixed placeholder set, sandboxed
     Jinja with autoescape.
  5. If match explanations are model-generated: prompt injection from CV text. Ranking itself is
     vector similarity and can't be steered by instructions in a CV; explanations must be treated
     as untrusted output and escaped.
- **Accepted risks for launch:** no malware scanning of uploads; [TODO — others].

## Audit / Logging

- **Audited actions:** see `data-model.md` > Change Auditing (applications via stage history;
  jobs, offers, approvals; company settings and templates). Staff/role changes are deliberately
  not audited.
- **Log retention:** [TODO].
- **Bulk operations:** the staff CSV import records a result per row in `import_row_results`; no
  per-record audit entry (users aren't audited).
