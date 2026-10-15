Problem & audience: TalentFlow is a multi-company hiring platform (an applicant
tracking system, or ATS). Small and mid-sized companies run hiring on email
threads and spreadsheets: CVs get lost, candidates wait weeks without updates,
interview feedback is inconsistent, and nobody can say how long hiring takes or
where good candidates come from. TalentFlow gives each company one place to open
a job, collect applications, move candidates through a pipeline, schedule
interviews, gather structured feedback, and make offers. Candidates get a portal
to apply and see where each application stands. It's a portfolio project, built
to show a production-style fullstack app on Azure.

Task:
- Recruiter (main user):
  - Draft a job requisition (title, department, location, employment type,
    remote policy, salary band min/max, headcount, description, requirements)
    and send it for approval. Approval: hiring manager, then company admin if
    the salary band is above the department's budget limit.
  - Publish an approved job to the company's public careers page; close or
    pause it. A job closes automatically when its headcount is filled.
  - Review applications. Uploaded CVs are parsed in the background (Azure AI
    Document Intelligence) into structured profile fields (name, email, phone,
    work history, education, skills). Possible duplicate candidates (same email
    or phone) are flagged for merging.
  - See AI-ranked applicants per job (Azure OpenAI embeddings + Azure AI
    Search) with a short explanation of the match. The ranking is advisory
    only and never rejects a candidate automatically.
  - Move candidates through a Kanban pipeline whose stages come from a
    company template (e.g. Applied → Screen → Interview → Offer → Hired, plus
    Rejected / Withdrawn). Single and bulk actions: move stage, reject with a
    reason and a templated email, tag, add a note. The board updates live for
    everyone viewing it (Azure SignalR).
  - Schedule interviews: pick interviewers, propose time slots, and let the
    candidate pick one. The app checks for conflicts against interviewers'
    existing TalentFlow interviews and emails invites with .ics attachments.
  - Track scorecards and chase late ones (automatic reminders).
  - Create an offer (salary, start date, terms) → approval chain (hiring
    manager; company admin if above the salary band) → PDF offer letter
    generated → candidate accepts/declines in the portal.
  - Search and tag the company's talent pool (past candidates) and invite them
    to apply for new jobs.
  - Reports: pipeline funnel conversion per stage, time-to-hire, candidate
    source breakdown, interviewer load. On-screen and CSV export.
- Hiring manager:
  - Approvals inbox (requisitions, offers), review the shortlist for their
    jobs, read scorecards, make the final hire / no-hire decision.
- Interviewer:
  - "My interviews" list, interview kit (questions per stage), structured
    scorecard (rating per competency + overall recommendation + notes).
- Candidate:
  - Sign up, maintain a profile and CV, apply to jobs at any company, track the
    status of each application, pick an interview slot, accept/decline offers,
    withdraw an application.
  - GDPR self-service: export their data, request deletion.
- Company admin:
  - Manage company users and roles, departments (with budget limits), pipeline
    templates, interview kits, email templates, careers page branding (logo,
    colour, intro text). Bulk-import staff users from CSV. View the company's
    audit log.
- Platform super-admin:
  - Onboard, suspend, and reactivate companies; assign a plan; see
    platform-wide stats. Plans limit usage (e.g. max active jobs, max staff
    seats), and limits are enforced by the app.
- System (background workers):
  - CV parsing, embedding/indexing for matching, email sending, interview and
    scorecard reminders, data-retention cleanup.

Roles & access:
- Platform super-admin: sees every company, but only platform-level data
  (companies, plans, usage stats). Never a company's candidates or
  applications.
- Company admin: everything inside their own company; nothing in other
  companies.
- Recruiter: acts on jobs they're assigned to; read-only on all other jobs in
  the company; the company-wide talent pool.
- Hiring manager: only jobs where they are the hiring manager, and the
  candidates in those jobs.
- Interviewer: only the interviews assigned to them and the candidate details
  needed for them. Other interviewers' scorecards for the same candidate stay
  hidden until they've submitted their own (blind scoring).
- Candidate: only their own profile and applications, across all companies.
  They never see internal notes, scorecards, tags, or AI match scores.
- One staff user can hold several roles inside their company (e.g. recruiter
  and interviewer).
- Data isolation between companies is enforced centrally (every
  company-owned record carries a company_id, and the scoping is applied in one
  place), not remembered per query.
- Authentication: Microsoft Entra External ID for everyone, staff and
  candidates. Candidates self-register. Staff accounts are created by a company
  admin (manually or by CSV import) and linked to an External ID identity on
  first login. Roles, company membership and active/inactive status live in
  TalentFlow's own database, not in the identity provider.

Stack & constraints:
- Backend: Python, FastAPI (I used FastAPI + React on my last project).
- Frontend: React + TypeScript, single-page app.
- Database: Azure Database for PostgreSQL (Flexible Server).
- Hosting: API on Azure Container Apps; frontend on Azure Static Web Apps.
- Background work: Azure Service Bus + Azure Functions (Python).
- Files (CVs, offer letter PDFs, company logos): Azure Blob Storage, served
  through short-lived SAS links, never public.
- AI: Azure AI Document Intelligence (CV parsing), Azure OpenAI embeddings +
  Azure AI Search (matching).
- Real-time: Azure SignalR Service. Email: Azure Communication Services.
- Auth: Microsoft Entra External ID.
- Secrets: Azure Key Vault + Managed Identity. No connection strings or keys
  in code or in git.
- Monitoring: Application Insights.
- Infrastructure as code: Bicep. CI/CD: GitHub Actions.
- Budget: personal Azure subscription. Prefer free/lowest tiers; anything
  with a meaningful monthly cost gets flagged to me before it's provisioned.
- Must run locally for development without requiring every Azure service to
  be live (local Postgres; emulators or fakes where reasonable).
- Build in phases, smallest useful slice first: single company, jobs → apply →
  pipeline. Multi-company, AI matching, real-time and the rest come in later
  phases, so there's always a working app.
- Open for the interview: ORM and migrations tool, test runner, frontend
  component library, and PDF generation library.

Non-goals (this version deliberately does NOT do):
- No real payments or billing. Plans and their limits exist, but nobody is
  charged; there is no Stripe or invoicing.
- No calendar sync with Google or Outlook. Availability and conflict checks
  only consider interviews booked inside TalentFlow; invites go out as .ics
  email attachments.
- No video interviews or built-in video calls. An interview can hold a
  meeting link pasted in by the recruiter.
- No posting to external job boards (LinkedIn, Indeed, etc.). Jobs are
  published only on the company's own careers page.
- No automated rejection or decision-making by AI. Matching ranks and
  explains; humans decide.
- No legally binding e-signatures. Offer acceptance is a recorded click
  in the portal, not a DocuSign-style signature.
- No background checks, assessments/coding tests, or reference-check
  integrations.
- No post-hire onboarding or HR system (HRIS) features. The process ends
  when a candidate is marked Hired.
- No native mobile apps. The web app is responsive; the candidate portal must
  work well on a phone, while staff screens are desktop-first.
- English only, single currency per company, no multi-language careers
  pages.
- A staff user belongs to exactly one company. (A candidate can apply to
  many companies.)
- No approval chains beyond the fixed ones described above. Approval steps
  are not configurable per company in this version.
- No in-app chat between candidates and recruiters. Communication is by
  templated email plus status updates in the portal.
- No custom domains for careers pages. They live under TalentFlow's URL with
  the company's slug.
- No SSO federation with a company's own identity provider (e.g. a customer's
  corporate Entra tenant or Okta).

---

Before asking me anything, read CLAUDE.md and every file in specifications/.
They tell you what needs filling in and which questions are worth asking.

Then interview me with AskUserQuestion, working through the spec files in this
order: functional.md, data-model.md, ui-guidelines.md, security.md,
performance.md, operations.md. Finish with a short pass on CLAUDE.md's Stack
and Commands — the test runner in particular, since that's a dependency you
shouldn't pick for me.

During the interview:
- Respect the gates. A section headed "Skip unless <trigger>" only applies if
  that trigger is actually true of this app. Check the trigger, and if it
  doesn't fire, skip the whole section and leave it in place unfilled — don't
  ask me its questions and don't delete it. If you can't tell whether a trigger
  fires, that one question is worth asking.
- Dig into the hard parts I probably haven't considered — concurrent writes to
  the same record, what happens to in-flight work when referenced data changes,
  delete and cascade behavior, where files are stored, how roles map onto
  accounts. The spec templates flag many of these; use them.
- Skip anything I've already answered above, and anything CLAUDE.md settles.
- "I don't know" and "no opinion" are valid answers. Record them as [TODO].
  Never invent a number, a target, or a policy on my behalf — a guess in a spec
  gets designed against, a [TODO] gets asked about.
- Batch related questions rather than asking one at a time. Aim for roughly
  6-10 rounds. Before your final round, show me a short list of what's still
  unresolved and let me decide what actually matters.

Then write the spec:
- Fill in the existing files under specifications/ in place. Don't create new
  spec files unless a feature or screen genuinely warrants one (see SPECS.md >
  Optional Extensions), and don't write a separate combined spec document.
- Fill in CLAUDE.md's Project, Stack, Commands, and Project Structure sections.
- Leave [TODO] wherever I didn't have an answer.
- Name the actual files, modules, and interfaces involved — not just concepts.
- Break the build into phases, smallest useful slice first. For each phase,
  name two things: what gets automated tests, and the end-to-end check I can
  run myself to confirm the phase works.

Then stop. Don't write application code until I've reviewed the spec and told
you to start.
