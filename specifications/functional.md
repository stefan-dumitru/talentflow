# Functional Specification

## Product Overview

- **What this is:** TalentFlow is a multi-company hiring platform (an applicant tracking system,
  or ATS). Each company opens jobs, publishes them on its own careers page, collects applications,
  moves candidates through a pipeline, schedules interviews, gathers structured feedback and makes
  offers. Candidates have one account they use to apply to any company and see where each
  application stands.
- **Who it's for:** Small and mid-sized companies' hiring teams (recruiters, hiring managers,
  interviewers, company admins), and the job candidates applying to them. Built as a portfolio
  project to show a production-style fullstack app on Azure.
- **Core problem:** Hiring run on email threads and spreadsheets loses CVs, leaves candidates
  waiting without updates, produces inconsistent interview feedback, and can't answer "how long
  does hiring take" or "where do good candidates come from."
- **Scope boundary — deliberately excluded:**
  - Real payments or billing. Plans and limits exist; nobody is charged.
  - Calendar sync with Google or Outlook. Conflict checks only see interviews booked in
    TalentFlow; invites go out as `.ics` attachments.
  - Video interviews. An interview can hold a meeting link pasted in by the recruiter.
  - Posting to external job boards (LinkedIn, Indeed, …). Jobs appear only on the company's own
    careers page.
  - Automated rejection or decision-making by AI. Matching ranks and explains; humans decide.
  - Legally binding e-signatures. Offer acceptance is a recorded click in the portal.
  - Background checks, assessments / coding tests, reference-check integrations.
  - Post-hire onboarding or HR system (HRIS) features. The process ends at Hired.
  - Native mobile apps. The web app is responsive (see `ui-guidelines.md`).
  - Multiple languages. English only; single currency per company.
  - Staff belonging to more than one company. A staff user belongs to exactly one company.
  - Configurable approval chains. The chains are fixed (see Use Cases).
  - In-app chat between candidates and recruiters.
  - Custom domains for careers pages.
  - SSO federation with a customer's own identity provider (their Entra tenant, Okta, …).
  - Recruiter-sourced candidates. Every candidate signs up themselves; recruiters can only invite
    existing talent-pool candidates to apply.
  - Duplicate-candidate detection and merging. Email is unique per account; that is the only
    duplicate rule in v1.
  - Offer expiry. Offers stay open until accepted, declined, or withdrawn.

## Authentication & Identity Source

- **Identity source:** External. Everyone (staff, candidates, super-admin) signs in through
  **Microsoft Entra External ID**. TalentFlow does not handle passwords.
- **Trusted claim:** The External ID user object ID (`oid`) is the stable identity key, stored as
  `users.external_id`. Email comes from the token and is stored for display and matching, but is
  not the identity key.
- **Resolved locally (TalentFlow's DB, never the identity provider):** whether the user is staff
  and in which company, their roles, active/inactive status, and whether they are a platform
  super-admin.
- Candidates self-register through External ID's sign-up flow. Staff accounts are created by a
  company admin (manually or by CSV import) with an email; the first time someone signs in with
  that email, the External ID identity is linked to the staff record.
- **One or the other:** a login is either staff (in exactly one company) or a candidate, never
  both. Adding a staff user whose email already belongs to a candidate account is blocked with
  "This email is used by a candidate account" — the person uses a work email instead.
- What happens for unknown or deactivated users is in `security.md` > Authentication.

## User Roles

A staff user can hold several roles in their company (e.g. recruiter + interviewer). Permissions
are the union of their roles.

| Role | Description | Can do | Cannot do | Data scope |
|---|---|---|---|---|
| Platform super-admin | Runs the platform | Onboard/suspend/reactivate companies, assign plans, see platform-wide usage stats, view and retry dead-lettered background jobs | See or change any company's jobs, candidates, applications, notes, scorecards or offers | Platform-level data only. Never company hiring data. |
| Company admin | Configures one company | Manage staff users and roles, departments (with salary cap), pipeline templates, interview kits, email templates, careers-page branding, retention period; CSV staff import; approve over-cap requisitions and above-band offers; view company audit log; everything a recruiter can do on any job | Act in another company; change the plan | Everything in their own company |
| Recruiter (main user) | Runs hiring for assigned jobs | Draft/edit jobs, publish approved jobs, manage applications on assigned jobs (move, reject, tag, note, bulk actions), schedule interviews, create offers, search talent pool and invite to apply, see reports | Act on jobs they aren't assigned to; approve their own requisitions/offers | **Read-only** on every job in the company; **act** only on jobs assigned to them (`job_recruiters`); full company talent pool |
| Hiring manager | Owns specific jobs | Approve/reject requisitions and offers for their jobs, review shortlist, read all submitted scorecards, make the hire / no-hire decision | Act on jobs they don't own | Only jobs where `jobs.hiring_manager_id` is them, and those jobs' candidates |
| Interviewer | Interviews candidates | See assigned interviews, the candidate details needed for them and the interview kit; submit a scorecard | See other interviewers' scorecards for a candidate **before submitting their own** (blind scoring); see anything outside assigned interviews | Only interviews they're a participant on |
| Candidate | Applies to jobs | Maintain profile and CV, apply, track applications, pick an interview slot, request a reschedule, accept/decline offers, withdraw, export their data, request deletion | See internal notes, tags, scorecards, AI match scores, other candidates | Only their own profile and applications, across all companies |
| System (background workers) | Azure Functions | Parse CVs, compute embeddings and index for matching, send emails, send reminders, run retention cleanup | Anything not triggered by a queue message or timer | Acts on the specific record in the message |

**Dashboards (aggregate stats, each needs its own summary endpoint):**

- **Recruiter:** assigned open jobs, new applicants since last visit, interviews this week,
  overdue scorecards on their jobs.
- **Hiring manager:** pending approvals, their open jobs with per-stage counts, shortlist awaiting
  review.
- **Company admin:** seats used vs. plan, active jobs vs. plan, hires this month, average
  time-to-hire.
- **Super-admin:** companies by status, total jobs / applications, usage per plan.

## Notifications

All email goes through Azure Communication Services, from templates. Company-facing emails use
the company's email templates (editable by the company admin); platform emails use fixed
templates.

| Recipient | Event | Channel |
|---|---|---|
| Candidate | Application received | Email + portal |
| Candidate | Interview invite (with `.ics`) and reschedule confirmations | Email + portal |
| Candidate | Offer sent | Email + portal |
| Candidate | Rejected — sent **immediately** when the recruiter rejects | Email + portal |
| Candidate | Any other stage move | Portal only |
| Interviewer | Interview invite / change / cancellation (with `.ics`) | Email |
| Interviewer | Scorecard reminder when overdue | Email |
| Hiring manager / company admin | Something awaits their approval | Email |
| Recruiter | Candidate requested a reschedule, accepted/declined an offer | Email + dashboard |

- Template content varies per company (each company edits its own); the set of events is fixed.
- Scorecard reminders: a scorecard is due 24 hours after the interview ends; once overdue, one
  reminder email per day until it's submitted.

## Search & Reporting

- **Talent pool search** (recruiter, company admin): candidates who have applied to this company
  at least once. Postgres full-text search over name, email, skills, CV text; filters on tag,
  source, last stage reached, applied date.
- **Job list** (staff): filter by status, department, recruiter, hiring manager; simple
  case-insensitive title match.
- **Careers page** (public): filter by department, location, employment type, remote policy;
  title keyword match.
- **Audit log** (company admin): filter by entity type, actor, date range.
- **Semantic matching** (AI ranking of applicants per job) uses Azure AI Search, not the
  keyword search above.
- **Reports** (recruiter, hiring manager for their jobs, company admin for all): pipeline funnel
  conversion per stage, time-to-hire, candidate source breakdown, interviewer load. On-screen and
  CSV export. No PDF reports.
- Reports are computed from `application_stage_history` at query time in v1. Whether that needs
  pre-aggregation is [TODO — decide once there's data to measure].

## Use Cases

### Job requisition approval and publishing

- **Role(s):** Recruiter (creates), hiring manager (approves), company admin (second approval when
  needed).
- **Trigger:** Recruiter clicks "New job" in the staff app.
- **Main flow:** Recruiter fills title, department, location, employment type, remote policy,
  salary band (min/max), headcount, description, requirements, hiring manager, pipeline template,
  assigned recruiters → saves as `draft` → submits → job becomes `pending_approval` and the hiring
  manager is emailed → hiring manager approves → if `salary_max` > department's `salary_cap`, a
  company-admin approval step follows → job becomes `approved` → recruiter publishes → `published`
  and visible on the careers page.
- **Rules & edge cases:**
  - Any rejection returns the job to `draft` with the approver's comment.
  - On creation the job **snapshots** its pipeline template's stages (`job_stages`); later
    template edits never affect existing jobs.
  - A published job can be edited freely; every change is audited. Raising `salary_max` above the
    department cap on a published job re-triggers the admin approval. The salary change is held
    as **pending** on the approval request; the job stays published with the old values until
    the admin approves (change applied) or rejects (change discarded).
  - Published jobs can be `paused` (hidden from the careers page, applications in flight continue)
    and `closed`. A job closes automatically when `hired_count` reaches `headcount`.
  - Remaining active applications on a closed job **stay active** — nothing automatic. The job
    shows "N candidates still active" with a bulk reject action (reason preset to "Position
    filled", rejection email sent as usual).
  - Publishing is blocked if the company is at its plan's active-job limit.
  - Edit conflicts: optimistic locking (see `operations.md`).

### Apply to a job

- **Role(s):** Candidate.
- **Trigger:** "Apply" on a careers-page job.
- **Main flow:** Not signed in → External ID sign-in/sign-up → back to the job → candidate
  confirms profile fields, picks or uploads a CV, answers nothing else (no custom questions in v1)
  → submits → `applications` row in the job's first stage → "application received" email →
  application visible in the portal.
- **Rules & edge cases:**
  - One **active** application per candidate per job. Re-applying is allowed once the previous one
    is rejected or withdrawn. Enforced by a partial unique index, so a double-submit can't create
    two.
  - Applying is blocked if the job isn't `published` or the company is suspended.
  - CV: PDF or DOCX, max 5 MB (see `security.md` > File Upload Handling).
  - **Proposed, confirm at review:** the application keeps a **snapshot** of the CV and parsed
    profile at the time of applying, so later profile edits don't change what the company
    received, and a company's retention purge deletes only its own snapshot.
  - `source` is recorded: `careers_page`, `talent_pool_invite`, or `direct_link`.

### CV parsing

- **Role(s):** System.
- **Trigger:** A CV is uploaded (profile or application).
- **Main flow:** API stores the file in Blob Storage, sets `cv_documents.parse_status = pending`,
  writes an outbox message → Function calls the Document Intelligence model → fills structured
  fields (work history, education, skills, raw text) → `parse_status = parsed`.
- **Rules & edge cases:**
  - Parsing never blocks the application; it's submitted immediately.
  - On repeated failure the message dead-letters, `parse_status = failed`, and recruiters see
    "parsing failed — profile fields entered by candidate only."
  - Re-delivered messages are no-ops if the document is already `parsed` (idempotent).
  - Which Document Intelligence model (prebuilt layout plus our own extraction, or a custom
    model): [TODO — decide in Plan Mode for that phase].

### AI match ranking

- **Role(s):** Recruiter, hiring manager (read).
- **Trigger:** Opening a job's "Ranked applicants" view.
- **Main flow:** Job text and each application's CV text are embedded (Azure OpenAI) and indexed
  (Azure AI Search). The view lists active applicants ordered by similarity with a short
  explanation.
- **Rules & edge cases:**
  - Advisory only: never moves, rejects, or hides a candidate.
  - Candidates never see match scores.
  - Unparsed or failed CVs appear at the bottom as "not ranked."
  - If AI Search is unavailable the view falls back to an unranked list with a banner.
  - How the explanation is produced (keyword/skill overlap vs. a generated summary): [TODO]. If
    generated by a model, CV text is untrusted input (see `security.md` > Threat Model).
  - Re-index when the job description changes or a CV is parsed.

### Pipeline stage moves (single and bulk)

- **Role(s):** Recruiter (assigned jobs), company admin.
- **Trigger:** Drag a card on the Kanban board, the keyboard "Move to…" menu, or a bulk action on
  selected applications.
- **Main flow:** Move → `applications.current_stage_id` updated → `application_stage_history` row
  (from, to, by, at, reason) → candidate sees new status in portal (no email except key events).
- **Rules & edge cases:**
  - Reject requires a reason from a fixed platform-wide list — Not enough experience, Skills
    mismatch, Better-qualified candidate, Salary expectations, Location/availability, Position
    filled, Other — plus an optional note, and sends the rejection email immediately.
  - Bulk actions (move, reject, tag) apply per application; failures (e.g. a version conflict on
    one) are reported per item, the rest succeed.
  - A stale move (the application changed since the board loaded) returns 409 and the card
    refreshes.
  - Moving into the Offer stage doesn't create an offer; the offer flow does.
  - Stages can't be deleted from a live job while applications are in them.

### Interview scheduling

- **Role(s):** Recruiter (schedules), candidate (picks a slot / requests reschedule), interviewers
  (notified).
- **Trigger:** Recruiter clicks "Schedule interview" on an application.
- **Main flow:** Recruiter picks the job stage, interviewers, duration, meeting link or location,
  and proposes several time slots → candidate is emailed → candidate picks a slot in the portal →
  the app books it for all interviewers in one transaction → `.ics` invites to everyone.
- **Rules & edge cases:**
  - Proposed slots are **not** held. If an interviewer got booked into an overlapping interview
    meanwhile, the pick fails with "slot no longer available" and the remaining slots are shown.
    Enforced by a Postgres exclusion constraint on the interviewer's time range, not just an app
    check.
  - Candidates can't reschedule or cancel themselves. They submit a **reschedule request**
    (with a message); the recruiter proposes new slots or keeps the booking.
  - Recruiters can cancel or reschedule; everyone gets an updated `.ics`.
  - Deactivated interviewers can't be picked (and deactivation is blocked while they have
    upcoming interviews — see Staff deactivation).
  - All times are stored UTC; emails state the time zone explicitly.

### Scorecard submission (blind)

- **Role(s):** Interviewer; recruiter and hiring manager read.
- **Trigger:** After the interview, from "My interviews."
- **Main flow:** Interviewer rates each competency from the stage's interview kit, gives an
  overall recommendation (`strong_no`, `no`, `yes`, `strong_yes`) and notes → submits → other
  submitted scorecards for that application become visible to them.
- **Rules & edge cases:**
  - Before submitting, an interviewer sees no other scorecards for that application.
  - Ratings are 1–5 per competency.
  - Due 24 hours after the interview ends; daily reminder emails while overdue.
  - **Locked after submission** — no edits, so nobody can adjust their score after reading
    others'.

### Hire decision and offer

- **Role(s):** Hiring manager (decision, approval), recruiter (creates offer), company admin
  (second approval when needed), candidate (accepts/declines).
- **Trigger:** Hiring manager marks an application "hire" (or "no hire," which rejects it).
- **Main flow:** Recruiter creates an offer (salary, start date, terms) → `pending_approval` →
  hiring manager approves → if salary > the job's `salary_max`, company admin approves → offer
  letter PDF generated (WeasyPrint) and stored → `sent`, candidate emailed → candidate accepts in
  portal → application `hired`, job `hired_count` + 1 → job closes when headcount is filled.
- **Rules & edge cases:**
  - At most one non-final offer per application (partial unique index).
  - No expiry. A sent offer can be `withdrawn` by the recruiter; changes mean withdraw + new
    offer.
  - Decline → application stays active in the Offer stage; the recruiter decides whether to make
    a new offer or reject. Accept/decline notify the recruiter by email + dashboard.
  - Accepting when the job is already filled or closed is blocked with an explanation.
  - Approver deactivated mid-chain: blocked by the deactivation rule (they must be reassigned
    first).

### Withdraw application

- **Role(s):** Candidate.
- **Trigger:** "Withdraw" in the portal.
- **Main flow:** Confirm → status `withdrawn` → stage history row → upcoming interviews
  cancelled and interviewers notified → any pending offer withdrawn.
- **Rules & edge cases:** Not allowed once `hired`. Can re-apply later (new application).

### Talent pool invite

- **Role(s):** Recruiter.
- **Trigger:** Select candidates in talent-pool search → "Invite to apply" for a published job.
- **Main flow:** Email with a link to the job; if they apply, `source = talent_pool_invite`.
- **Rules & edge cases:** Candidates with an active application to that job are skipped and
  reported. Anonymized candidates never appear.

### Staff deactivation

- **Role(s):** Company admin.
- **Trigger:** "Deactivate" on a staff user.
- **Main flow:** The app lists the user's open items (assigned jobs where they're the only
  recruiter, jobs they're hiring manager for, pending approvals, upcoming interviews) → admin
  reassigns each → deactivation completes → their sign-in now gets the
  "account disabled" page.
- **Rules & edge cases:**
  - Blocked until every open item is reassigned. Nothing is left orphaned.
  - The last active company admin can't be deactivated.
  - Unsubmitted scorecards don't block deactivation; they close as **not submitted**, visible to
    the recruiter and hiring manager.
  - Reactivation is allowed: the admin reactivates, previous roles return, and the user counts
    against seats again.

### Staff CSV import

- **Role(s):** Company admin.
- **Trigger:** Upload a CSV on the Users page.
- **Main flow:** Single mode: **add + update**, matched on email (case-insensitive). New email →
  staff user created. Existing email → name, department, roles updated. An `import_runs` record
  tracks status and counts, with a result per row.
- **Rules & edge cases:** Full rules in `data-model.md` > Bulk Operations. Never deactivates
  anyone. Seats limit from the plan applies.

### GDPR export and deletion

- **Role(s):** Candidate (requests), system (executes).
- **Trigger:** "Export my data" / "Delete my account" in the portal.
- **Main flow:**
  - Export: a JSON file (profile, applications, statuses, interview times, offers, **and** the
    internal notes and scorecards about them — GDPR's right of access covers personal data held
    about the person) prepared in the background and offered as a short-lived download. Staff UI
    states that notes and scorecards can be exported by the candidate.
  - Deletion: confirm → active applications withdrawn → personal data **anonymized**: name,
    contact details, CV files, parsed fields, notes about them, tags; application rows kept
    anonymously so reports and the audit trail stay intact → External ID account
    **deleted** through Microsoft Graph (needs a Graph permission on the app registration).
- **Rules & edge cases:** Irreversible; requires re-confirmation. Hired applications are
  anonymized too on a deletion request. The person can later sign up again as a new candidate.

### Retention purge

- **Role(s):** System (nightly timer).
- **Trigger:** Timer.
- **Main flow:** For each company with `retention_months` set, anonymize that company's
  application snapshots, notes and tags for candidates whose last activity with that company is
  older than the period.
- **Rules & edge cases:** Never touches active or **hired** applications (hired people are now
  employees; a candidate's own deletion request still covers them). Default period when a company
  hasn't set one: 12 months.

### Company onboarding, plans and suspension

- **Role(s):** Platform super-admin.
- **Trigger:** "New company" in the platform admin area.
- **Main flow:** Create company (name, slug, currency, time zone, plan) + first company admin's
  email → admin signs in and sets up departments, templates and branding.
- **Rules & edge cases:**
  - Plan limits: max active (published) jobs and max active staff seats — **Free** 2 jobs / 3
    seats, **Pro** 10 / 15, **Business** 50 / 100. Exceeding a limit blocks the action with a
    message; it never deletes data.
  - Downgrading below current usage is allowed and **grandfathered**: nothing is closed or
    deactivated, but new publishes / new seats are blocked until usage is under the limit, and the
    admin dashboard shows a warning.
  - The company `slug` is immutable for company admins; only the super-admin can change it (old
    links break — no redirects in v1).
  - **Suspension:** staff can sign in and view/export but every write is rejected; careers page
    and applying are disabled; candidates with in-flight applications see "hiring paused."
    Background jobs for that company (reminders) pause. Reactivation restores everything.

---

## Build Phases

Smallest useful slice first. Each phase ends with a running app. Each is planned in Plan Mode
before building. "Tests" = automated; "Check" = what you run yourself.

| # | Phase | Tests | Check |
|---|---|---|---|
| 0 | **Skeleton & tooling:** `backend/` (FastAPI, uv, Ruff, mypy, pytest), `frontend/` (Vite React TS, shadcn/ui on Radix, oxlint, Vitest), `docker-compose.yml` (Postgres on host port 5433, Azurite), Alembic baseline, `/health/live` + `/health/ready`, request-id middleware and generic 500s, GitHub Actions running lint + type check + tests + build (Playwright joins in Phase 3) | Health endpoints (ready returns 503 when the DB is down; live stays 200); request-id handling and generic 500; frontend status states (checking, ready, 503, unreachable, retry) and system dark-mode following | `docker compose up -d`, run API + frontend, open `http://localhost:5173` and see "API and database ready"; stop Postgres, click Retry, see "API unavailable" |
| 1 | **Identity, tenancy & roles:** External ID sign-in (MSAL in SPA, JWT validation in API), `users`, `companies`, `staff_members`, `staff_roles`, `Principal` dependency, `require_roles`, central company scoping, seed CLI for two companies | Token validation (bad signature/audience/expiry rejected); unknown user → candidate; deactivated staff → denied; **cross-company isolation** (company A can't read B's records by ID) | Sign in as a candidate and as a staff user; each sees its own shell |
| 2 | **Jobs & careers page:** departments, pipeline templates, jobs (draft/edit/publish, no approvals yet), stage snapshot, public careers page | Job state transitions; stage snapshot independent of template edits; optimistic-lock 409; careers page shows only published jobs of that company | Create and publish a job; see it at `/careers/<slug>` |
| 3 | **Apply & pipeline board:** candidate profile, CV upload to Blob (Azurite), apply, one-active rule, Kanban board (drag + keyboard), stage history, notes, tags, reject/withdraw, talent-pool full-text search | One-active-application rule (incl. double submit); upload type/size validation; recruiter can't act on unassigned job but can read it; candidate can't see notes/tags | Apply as a candidate, move them across the board as a recruiter, see status in the portal |
| 4 | **First Azure deployment:** Bicep (`infra/`), Container Apps, Static Web Apps, PostgreSQL, Blob, Key Vault + Managed Identity, App Insights, deploy workflow | Bicep lint/what-if in CI | Phases 1–3 flow works on the production URL; logs appear in App Insights |
| 5 | **Approvals, audit & deactivation:** requisition approval chain, approvals inbox, `audit_log`, staff deactivation with reassignment | Approval chain incl. over-cap admin step; rejected → draft; audit rows with old→new values; deactivation blocked with open items; last admin protected | Submit a job, approve as HM then admin, see audit entries |
| 6 | **Background processing & email:** Service Bus, Azure Functions app, transactional outbox, ACS email templates, CV parsing, DLQ admin view | Outbox written in same transaction; idempotent handlers (redelivery = no-op); parse failure → `failed` status | Upload a CV, see parsed fields appear; receive the "application received" email |
| 7 | **Interviews & scorecards:** interview kits, slot proposals, booking with exclusion constraint, `.ics`, reschedule requests, blind scorecards, reminders | Overlapping booking rejected by the DB; blind visibility; reschedule request flow | Schedule an interview, pick a slot as candidate, receive `.ics`, submit two scorecards |
| 8 | **Offers & hiring:** hire decision, offer + approval chain, WeasyPrint PDF, accept/decline, auto-close at headcount | Above-band admin step; one open offer per application; accept on filled job blocked; auto-close | Full flow from application to Hired; download the offer PDF |
| 9 | **Platform admin:** company onboarding, plans and limits, suspension, branding, retention setting, staff CSV import | Limit enforcement; suspended company is read-only; import rules (dup rows, invalid rows, last-wins) | Onboard a second company, import staff, suspend and reactivate it |
| 10 | **Dashboards & reports:** four dashboards, funnel / time-to-hire / source / interviewer-load reports, CSV export | Report numbers on a fixed fixture dataset; scope (HM sees only their jobs) | Compare dashboard numbers against seeded data |
| 11 | **AI matching:** embeddings, AI Search index, ranked-applicants view, fallback | Ranking order with a fake embedding client; fallback when search is down; candidate can't access scores | Ranked list for a job with a few real CVs |
| 12 | **Real-time board:** SignalR live updates on the pipeline board | Event published on stage move; board applies remote change | Two browsers on the same board; a move in one appears in the other |
| 13 | **GDPR & retention:** export, deletion/anonymization, nightly retention purge | Anonymization removes PII but keeps report counts; retention respects active applications | Delete a test candidate; confirm their data is gone and the funnel numbers didn't change |
