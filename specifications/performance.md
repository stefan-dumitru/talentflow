# Performance Requirements

Only fill in numbers you actually care about. A vague "should be fast" gives Claude nothing to
design against — a target latency or load figure does. Leave `[TODO]` rather than guessing.

Targets below are **demo scale**: a portfolio deployment, not a commercial launch.

## Response Time Targets

| Operation | Target (p50) | Target (p95) | Notes |
|---|---|---|---|
| Page load / initial render | [TODO] | [TODO] | |
| API read (simple) | [TODO] | < 300 ms | Demo-scale target |
| API write | [TODO] | [TODO] | |
| Pipeline board load (one job) | [TODO] | [TODO] | Heaviest staff read |
| Report queries | [TODO] | [TODO] | Computed from stage history at query time |

## Scale Expectations

- **Concurrent users:** ~50 at demo scale, across ~10 companies. At 1 year: [TODO].
- **Data volume:** [TODO — largest tables will be `application_stage_history`, `audit_log`,
  `applications`].
- **Read/write ratio:** [TODO — expected read-heavy].
- **Spiky load:** nightly retention job; bulk actions on the board; staff imports. [TODO — sizes].

## Constraints This Implies

- **Pagination required on:** every list endpoint — jobs, applications, talent pool, audit log,
  approvals, interviews, import results, careers page, platform companies, failed jobs. Page size
  25 by default, 100 max. The pipeline board loads 50 cards per stage, then "load more."
- **Caching:** none in v1, except the External ID JWKS keys (cached in-process until key
  rotation; read-only public data, so this doesn't break statelessness). [TODO — revisit with
  measurements.]
- **Background/async processing:** CV parsing, embedding and search indexing, all email, offer
  PDF generation [TODO — sync or async?], GDPR exports and deletions, retention purge, reminders.
  Staff CSV import is synchronous (max 1,000 rows).
- **Database indexing priorities:**
  - `company_id` leading every composite index on company-owned tables.
  - `applications (job_id, current_stage_id) WHERE status = 'active'` — board.
  - Partial unique `applications (candidate_user_id, job_id) WHERE status = 'active'`.
  - `application_stage_history (company_id, occurred_at)` and `(application_id)` — reports.
  - GIN on `cv_documents.search_vector` — talent pool full-text search.
  - GiST exclusion on `interview_participants (staff_member_id, during)`.
  - `audit_log (company_id, entity_type, entity_id)` and `(company_id, occurred_at)`.
- **Debounce for search inputs:** 300 ms.

## Frontend Performance Budget

- **Initial JS/CSS bundle:** [TODO]. Route-level code splitting by shell (public / candidate /
  staff / platform) so careers-page visitors don't download the staff app.
- **Core Web Vitals targets:** [TODO — matters most for public careers pages].
- **Images:** only company logos; served from Blob at a fixed max size, lazy below the fold.
  [TODO — resize on upload?]
- **Fonts:** Inter, self-hosted as a variable WOFF2 font, `font-display: swap`, preloaded.

## Bulk / File Operation Performance

- **Expected sizes:** CVs ≤ 5 MB each. Staff CSV: ≤ 1,000 rows. Board bulk actions: [TODO — max
  selected items per action].
- **Processing time / async threshold:** CV parsing is always async. Staff import is synchronous;
  the 1,000-row cap keeps it within a request. [TODO — processing time target.]
