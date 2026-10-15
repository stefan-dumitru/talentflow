# Specifications — Index

This folder holds the specification for what you're building. Durable, cross-project conventions
(coding style, git conventions, security baseline) live in [../CLAUDE.md](../CLAUDE.md) instead —
that file is auto-loaded every session, this folder is read selectively.

Specs are split by concern so you can update one without touching the others, and so you can hand
Claude only the file(s) relevant to the feature you're working on rather than the whole document.

| File | Covers |
|---|---|
| [functional.md](functional.md) | Product overview, user roles, use cases / user stories, in/out of scope, build phases |
| [data-model.md](data-model.md) | Entities, master data vs. transactional data, relationships |
| [ui-guidelines.md](ui-guidelines.md) | Design system, branding, key flows, accessibility |
| [security.md](security.md) | Auth/authz model, data protection, compliance, threat model |
| [performance.md](performance.md) | Response time targets, scale expectations, caching, pagination, frontend budget |
| [operations.md](operations.md) | Availability, observability, migrations, background jobs, integrations, concurrency, scaling constraints |

## Two rules these files follow

**Invariants live in `CLAUDE.md`, decisions live here.** Anything true of every project — use
parameterized queries, hash passwords, authorize before acting — belongs in `CLAUDE.md`, which is
loaded every session. These files hold only what varies per app. Where a spec file needs to
mention an invariant for context, it states it as a given and points at `CLAUDE.md` rather than
restating the rule. A rule written as a `[TODO]` reads as optional, which is exactly wrong.

**Sections are gated.** A section headed with a `> **Skip unless** …` blockquote doesn't apply to
every project. The trigger is always something concrete you can check — "this app accepts file
uploads," not "the project is complex." Skipping a gated section is free; skipping an ungated one
is a decision you should make deliberately.

## How to use this per project

1. Copy this whole repo (`CLAUDE.md` + `specifications/`) as the starting point for a new app.
2. Fill in `first-prompt.md` and give it to Claude. It reads these files, interviews you, and
   fills them in — you don't fill them by hand first. Answer "I don't know" freely; it becomes a
   `[TODO]`, which is always better than a guess baked in early.
3. Review what it wrote. This is the step that matters — the interview surfaces decisions, but
   they're still yours. Anything left `[TODO]` is a question you can come back to.
4. Start building. For each feature: open Plan Mode, point Claude at the relevant spec file(s),
   review the plan, then build. Don't try to resolve every `[TODO]` before writing any code —
   for a complex app you will discover requirements while building, not before.
5. When a feature reveals the spec was wrong or incomplete, update the spec file as part of that
   feature's work, not as separate cleanup later.

## Optional Extensions

Not created by default — add these only when a feature or the project's size genuinely needs them:

- **`pages/<page-name>.md`** — a full spec for one screen (layout per breakpoint, interactions,
  API calls, state, error states) when that screen is complex enough that Plan Mode alone risks
  missing something. See `ui-guidelines.md` > Per-Screen Specification Files.
- **`features/<feature-name>.md`** — a full spec for one complex feature's business rules (e.g. a
  multi-mode import/export process), when the rules have enough edge cases that they don't fit
  cleanly as a `functional.md` use case. See `functional.md` > Use Cases.
- A phased, dated implementation plan with milestones and sign-off is a reasonable choice for a
  larger team or a client-facing project with formal checkpoints — it trades the iterative
  approach's flexibility for more upfront predictability. This template defaults to iterative
  because that trade usually isn't worth it for a solo/AI-assisted build, but it's a legitimate
  choice when made deliberately, not a mistake.

## What's deliberately *not* here

- **Execution / Testing / Deployment** aren't spec sections in this template. They're workflow —
  they happen via the plan → build → test → commit loop per feature (and CI/deployment config
  once you have one), not a document you write once upfront. Trying to spec "testing" in the
  abstract before any code exists tends to produce boilerplate that doesn't match what the app
  actually needs tested. The standing rules for how testing is done live in `CLAUDE.md` >
  Testing; what "finished" means is `CLAUDE.md` > Definition of Done.
- **Design of individual screens/modules** isn't a separate phase either — it happens inside Plan
  Mode for the feature that needs it, informed by `ui-guidelines.md` and `data-model.md`. Only the
  durable, cross-feature design decisions (design system, branding, overall IA) belong in
  `ui-guidelines.md`.
