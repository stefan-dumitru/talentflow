# UI / Design Guidelines

Only the cross-feature, durable design decisions go here. Layout of an individual screen belongs
in that feature's Plan Mode session, informed by this file — not spec'd upfront here.

## Design System

- **Component library:** shadcn/ui (components copied into `frontend/src/components/ui/`) on
  Tailwind CSS and Radix UI primitives.
- **Brand colors / typography:** Indigo primary on shadcn/ui's neutral greys; Inter, self-hosted
  (no request to Google Fonts). Exact shades are set as theme tokens in Phase 0. Company careers pages
  use the company's `brand_color` as the accent only; it's rejected on save if it fails WCAG AA
  contrast against the text drawn on it.
- **Light/dark mode:** both. Defaults to the OS setting; a toggle in the user menu overrides it
  (stored per browser).
- **Responsive targets:**
  - Careers pages and the candidate portal: **must** work on phones, tablets and desktop.
  - Staff app (recruiter, HM, interviewer, admin) and platform admin: **desktop-first**; tablet
    best-effort; phone not supported in v1 **except** "My interviews" and scorecard submission,
    which must work on phones (interviewers often submit right after the interview).
- **Breakpoints:** Tailwind defaults (`sm` 640, `md` 768, `lg` 1024, `xl` 1280). Layout change at
  each: [TODO — e.g. staff sidebar collapses below `lg`].
- **Component structure:** feature folders — `frontend/src/features/<feature>/` holds that
  feature's pages, components, API hooks and tests. Shared primitives live in
  `frontend/src/components/ui/` (shadcn) and `frontend/src/components/` (app-wide composites).
- **Browser support:** last 2 versions of Chrome, Edge, Firefox and Safari, including iOS Safari
  and Android Chrome for the phone-supported screens. Playwright runs on Chromium, plus WebKit for
  candidate flows.

## Information Architecture

Separate shells, chosen after sign-in by what the user's DB record says:

- **Public** (no sign-in): `/careers/<company-slug>` (job list), `/careers/<company-slug>/jobs/<id>`.
- **Candidate portal** (top nav): My applications, Profile & CV, Interviews, Offers, Privacy (export
  / delete).
- **Staff app** (left sidebar; items shown by role):
  - Dashboard (all staff — content per role)
  - Jobs (recruiter, HM, admin) → job detail with tabs: Pipeline board, Ranked applicants,
    Details, Activity
  - Talent pool (recruiter, admin)
  - Approvals (HM, admin)
  - My interviews (interviewer)
  - Reports (recruiter, HM, admin)
  - Settings (admin): Users, Import, Departments, Pipelines, Interview kits, Email templates,
    Branding, Retention, Audit log
- **Platform admin** (super-admin only, separate area): Companies, Plans, Failed jobs, Usage.
- A user with several roles sees the union of their sidebar items. A suspended company's staff
  see a persistent "read-only — company suspended" banner and disabled write actions.

## Key Flows

- **Apply:** careers page → job → sign in/up (External ID) → back to the same job → confirm
  profile + CV → submitted → portal. The return-to-job after sign-up must not lose the job.
- **Requisition to published job:** draft → submit → approvals inbox (HM, maybe admin) → recruiter
  publishes. The job's status is always visible as a step indicator on the job page.
- **Interview scheduling:** recruiter proposes slots → candidate picks in portal → confirmation
  screens for both sides, with times in the viewer's zone and the zone named.
- **Offer:** create → approvals → candidate sees offer + PDF → accept/decline → hired.
- **New company onboarding:** super-admin creates → first admin's first sign-in lands on a setup
  checklist (departments, pipeline template, branding, invite staff).

The pipeline board is complex enough to get its own `pages/pipeline-board.md` when Phase 3 is
planned.

## Accessibility

- **Target:** WCAG 2.2 AA.
- **Specific requirements:**
  - Everything keyboard-operable. The pipeline board's drag-and-drop has a keyboard equivalent:
    a "Move to…" menu on each card (WCAG 2.2 "dragging movements").
  - All form fields labelled; errors announced and linked to their field.
  - Live updates on the board are announced politely (`aria-live`) without stealing focus.
  - Colour is never the only signal (statuses have text/icon as well).
- **Touch targets:** 44×44 CSS px on candidate-facing pages and the phone-supported interviewer
  screens; 24×24 px (WCAG 2.2 AA minimum) on desktop-first staff screens.

## Feedback & Error States

- **Error messages by category:**
  - Validation (422): per-field, inline, next to the field.
  - Conflict (409, optimistic lock): "This was changed by someone else. Reload to see the latest
    version." with a Reload button; the user's unsaved input is kept visible until they reload.
  - Authorization (403): "You don't have access to this." No detail about why.
  - Suspended company (writes): "Your company's account is suspended; changes are disabled."
  - Network / server (5xx): a toast "Something went wrong — try again," plus a request id the user
    can quote.
- **Success messages:** toast for routine actions (saved, moved, sent). Irreversible actions
  (reject, withdraw, GDPR delete, deactivate) get a confirmation dialog **before**, then a toast.
- **Loading:** skeletons for page/list loads; the triggering button is disabled with a spinner
  while its request is in flight (prevents double-submit). Long background work (CV parsing,
  imports, exports) shows a status chip (`Pending` / `Processing` / `Done` / `Failed`) instead of a
  blocking spinner.
- **Empty states:** every list has one with a next action ("No jobs yet — Create a job"), distinct
  from "no results for this filter."
- **Client vs. server validation:** the server (Pydantic) is the source of truth. The frontend
  uses TypeScript types generated from the API's OpenAPI schema; client-side checks are limited to
  required fields and formats for convenience. Generated types: `openapi-typescript`, with
  `openapi-fetch` as the typed API client (regenerated whenever the API schema changes).
- **Session expiry:** MSAL renews tokens silently. If renewal fails mid-form: [TODO — e.g. keep
  form state in memory, re-authenticate in a popup, then retry the request].

## Localization & Formatting

- **Languages:** English only, and that won't change in v1 (see `functional.md` non-goals).
- **Formatting:** dates, numbers and money via the browser's `Intl` APIs using the viewer's
  locale. Money is always in the company's `currency`.
- **Time zone for display:** the **viewer's own** zone (from the browser; overridable in profile
  [TODO — needed?]). Emails can't know the viewer's zone, so they state times with the zone named
  explicitly — the recipient's profile zone if known, otherwise the company's `time_zone`.
- **RTL:** not needed.

## Per-Screen Specification Files

For an app with many distinct screens, don't try to capture every screen's layout in this file —
give a genuinely complex screen its own spec instead: `specifications/pages/<page-name>.md`,
covering: overview, which roles see it and what each can do, layout per breakpoint,
features/interactions, which entities from `data-model.md` it reads/writes, API endpoints it
calls, state it manages, error states, and any mobile/accessibility notes specific to that
screen.

Only write one when a screen is complex enough that Plan Mode alone would risk missing something
— not for every screen by default. Doing this for every screen upfront is exactly the
over-specification this template's default workflow (see `SPECS.md`) is trying to avoid.

Planned: `pages/pipeline-board.md` (Phase 3).
