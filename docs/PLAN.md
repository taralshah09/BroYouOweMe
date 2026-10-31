# BroYouOweMe: Feature Definition and Phase Plan

Status: Phases 0 through 4 validated. Phases 5 through 7 implemented; the owner reports voice logging works. Phase 7 tests and a full page-structure audit pass. Representative desktop and all 21 mobile page-state visual checks are complete; real-device interaction QA and a real receipt-photo trial remain pending. The group lifecycle gap identified by the audit is implemented in the 2026-10-31 follow-up; see `docs/UI_AUDIT.md`.
Source: `Assignment.pdf` (Decentro SDE Intern, Expense Sharing Service) plus extra requirements.

## Locked decisions

| Area | Decision |
|---|---|
| Backend | Python, Django, server-side rendered |
| Frontend | Plain HTML, CSS, JS served by Django templates. No React. |
| Database | PostgreSQL on Neon |
| Auth | Django session auth. Signup with email and username (both unique); login with either. No email verification for now. |
| API | SSR pages plus JSON endpoints matching the assignment (`/signup`, `/groups`, `/groups/{id}/members`, `/expenses`, `/groups/{id}/expenses`, `/balances`) |
| Money | INR only, stored as integer paise. Remainder paise are assigned deterministically so splits always sum to the total. |
| Members | Registered users only. No guest placeholders. |
| Voice transcription | Sarvam, transcription only. Comma-separated SARVAM_API_KEYS chained as fallbacks in order. Endpoint and limits verified in Phase 6. |
| Voice languages | Hinglish (the reason Sarvam was chosen) |
| Parsing / tool calling | Groq free tier running an open-source OpenAI model (gpt-oss), called through the OpenAI SDK pointed at Groq's OpenAI-compatible endpoint. Turns transcripts into structured expenses and handles tool calling. Exact model (20B vs 120B) to pick after checking Groq's current free-tier limits and tool-calling support. |
| Groups | Multiple admins per group. An admin can promote other members to admin, change roles, and remove other members, including other admins (removal needs zero balances). The last admin cannot leave until they make another member admin (no auto-promotion). |
| Settlements | Confirmation required: payer claims, receiver confirms (or rejects). Balance changes only on confirmation. |
| Render plan | Free tier, kept awake by an external pinger hitting a health URL. Deployed via Docker (Tesseract binary). Uploads processed in memory, not stored. |
| Invites | Links expire and are multi-use. Only admins can create and revoke them. |
| Expense permissions | Only the creator of an expense can edit or delete it. Admins cannot. |
| Neon | Pro plan |
| Hosting | Render |
| Receipt OCR | Tesseract, self-hosted. Needs a manual-correction screen. |
| UPI / Google Pay linking | Dropped entirely |
| Personal user QR | Dropped entirely |

## Schema decisions (so far)

| Topic | Decision |
|---|---|
| Primary keys | Auto-increment integers (matches the assignment). Every view must check group membership strictly, because IDs are guessable. |
| Balances | Maintained balance table, updated in the same DB transaction as every expense create/edit/delete and every confirmed settlement. Because this can drift, there will also be a recompute-from-ledger function used by tests and an integrity check. |
| Edit/delete | Expenses are soft-deleted. Edits overwrite the row, and the activity log stores before/after values. |
| Balance scope | Per group (`GET /groups/{id}/balances`) plus an overall view for the logged-in user (`GET /balances`). |
| User identity | Username is the identity everywhere (unique, case-insensitive). Users also have a unique email, and an account can be created from an email. No separate display name. The balances JSON is keyed by username. |
| Receipt items | Stored in an items table behind the expense. The uploader is the payer of the whole bill. Before logging, the uploader reviews the extracted items once and can assign each item to other members. |
| Receipt split modes | Two modes on the review screen: equal share (whole bill split among the chosen participants) or itemised (select which items belong to each payee, so each person pays only for what they ordered). |
| Shared receipt items | An item can have several payees, and its price is split equally among them. |
| Tax / service charge / tip / discount | Itemised mode splits these equally among payees (everyone with at least one item). Rounding remainders are assigned deterministically so totals always match. |
| Invite links | Fixed 7-day expiry for every link, no per-link options, admins can revoke. |
| Unassigned receipt items | In itemised mode, an item with no payee defaults to being split among all participants. |
| Group deletion | An admin can delete a group only when all balances are zero. It is soft-deleted (hidden, kept for audit). |
| Leaving a group | Blocked until all the member's balances in that group are zero. The admin-handover rule still applies on top. |
| Participants | Any subset of the group, defaulting to all members. Stored as per-user split rows. |
| Expense date | Separate `expense_date` (defaults to today, can be backdated) plus `created_at`. Analytics use `expense_date`. |
| Categories | Built-in defaults (Food, Travel, Stay, Shopping, Entertainment, Utilities, Other) plus categories created per group that are visible only inside that group (e.g. "Booze" on the Goa Trip group). Any member can manage them; a category used by any expense cannot be deleted. Expenses also keep an optional free-text tag. |
| Settlements | Partial amounts allowed, from 1 paisa up to the current amount owed to that person in that group. Overpayment is rejected. |

## Feature list

### Assignment-mandatory
1. Create accounts through signup; global listing removed at owner request for privacy.
2. Create groups
3. Add users to a group and list members
4. Add an expense (equal split among all group members; validation: amount > 0, valid group, payer does not owe themselves)
5. List a group's expenses
6. Balances API (structured: `{"Rahul": {"owes": {"Mohit": 400}}}`)
7. Product Enhancement (explained: why, problem solved, design decisions, tradeoffs). Covers all extras below.

### Assignment-optional (included)
8. Settlements (payer marks paid, receiver confirms)
9. Unequal splits
10. Unit tests (expense creation, balance calculation, validation)
11. Docker setup

### Your additions
12. Receipt image upload with OCR; items logged as expenses, with per-item assignment and equal charges among people with items
13. Voice logging with an explicit approval screen before anything is saved
14. Invite via link or QR (non-users sign up first, then auto-join)

### Standout extras
15. Debt simplification (minimum number of transfers)
16. Activity feed (audit trail of every expense, edit, and settlement)
17. Categories, monthly analytics, CSV export, settle-up nudges

## Phases

### Phase 0: Foundations
- Django project and app layout, env-based config, Neon connection
- Money utilities (paise, rounding/remainder allocation)
- Dockerfile and docker-compose (Tesseract binary included)
- Exit: app boots locally and in Docker, connects to Neon.

Completed and verified on 2026-10-30:
- Django project and seven domain app packages; models and auth remain Phase 1 work.
- Environment-only secrets, PostgreSQL URL configuration, connection health checks,
  SSR placeholder, static assets, and database-backed `/health` endpoint.
- Exact paise conversion and deterministic equal allocation, including discount totals.
- Docker image with Gunicorn, WhiteNoise and Tesseract, running as a non-root user;
  Compose uses the configured Neon database.
- Django system checks and 12 tests passed locally and inside Docker.
- Local and Docker HTTP checks passed for `/` and `/health` against Neon;
  collected CSS and the Tesseract binary were verified in Docker.
- No migrations applied; the custom user model must precede the first migration.

### Phase 1: Core assignment (a complete submission on its own)
- Models: user, group, group membership, expense
- Auth: signup, login, logout
- Endpoints and SSR pages for users, groups, members, expenses
- Equal-split logic and balances API
- Validation rules from the assignment
- Unit tests for expense creation, balances, validation
- Exit: the Example Scenario (Mohit/Rahul/Ankit, Dinner 1200) produces the exact expected JSON.

Completed and verified on 2026-10-30:
- Custom user model and initial migrations; case-insensitive email/username
  signup and login, hashed passwords, session auth, CSRF-protected logout.
- Groups with creator-admin membership and admin-only additions; membership
  checks on every group read and expense operation.
- Equal-split manual expenses, deterministic rounding, maintained pairwise
  balances, group locking, atomic PostgreSQL upserts, and integrity command.
- SSR pages and JSON endpoints for accounts, groups, members, expenses, and
  group/overall balances. API usage is documented in `docs/API.md`.
- The exact Mohit/Rahul/Ankit Dinner 1200 balance JSON passes end to end.
- 38 tests pass locally and in Docker, including partial-write rollback,
  concurrent creation, overflow validation, CSRF, and historical membership.
- Initial migrations applied on Neon; database integrity and HTTP health pass.
- WSGI database connections are reused for up to 60 seconds by default, with
  health checks enabled; `DB_CONN_MAX_AGE` can override this (`0` for ASGI).
- Browser signup, group creation and expense submission verified against a
  disposable local database; desktop and mobile layouts visually inspected.
- Phase 1 implicit shares use membership join times, not expense dates. Phase 2
  must materialize them before edits or member removal/rejoining are enabled.

### Phase 2: Ledger
- Per-user split rows (replaces implicit equal split) and unequal splits
- Expense edit and delete
- Settlements: record, confirm, and reflect in balances
- Activity feed
- Categories: seeded defaults, per-group custom categories (any member manages; rename allowed; delete blocked once in use), free-text tag, and category on expenses
- Exit: every balance can be traced to events, and editing an expense updates balances correctly.

Completed and verified on 2026-10-30:
- Explicit positive per-user shares for equal, subset, and exact unequal splits;
  atomic migration preserves Phase 1 historical participants and balances.
- Creator-only expense edits and soft deletion, with allocation reversal and
  before/after activity snapshots committed in the same transaction.
- Partial settlement claims, receiver confirmation/rejection, payer cancellation,
  pending-debt reservation, and confirmation-time overpayment checks under locks.
- Seven seeded defaults, member-managed custom categories, protected historical
  use, optional tags, and expense category/date/search filters.
- Paginated activity JSON and SSR feed, split-aware browser forms, expense editing,
  category management, and settlement screens.
- Integrity command verifies explicit share totals and recomputes expenses plus
  confirmed settlements. No balance drift after the configured Neon migration.
- 60 tests pass locally and in Docker, including migration backfill, rollback,
  creator permissions, malformed inputs, category scope, and concurrent claims
  and confirmations. Django checks and migration consistency checks pass.
- Browser unequal creation/editing and payment claim/confirmation verified on
  disposable PostgreSQL; desktop/mobile screenshots inspected, no horizontal
  overflow or JavaScript errors. Docker `/health` returns 200 against Neon.
- Phase 2 migrations applied to Neon and the local Docker app rebuilt/restarted.
  The data transition is intentionally irreversible; stop Phase 1 workers before
  migration because they cannot create explicit splits.

### Phase 3: Debt simplification
- Minimum-transfer algorithm over net balances
- Tests, including cycles and uneven totals
- "Suggested settlements" view (display only; settlements stay between real pairwise debts)
- Exit: explanation of the algorithm and its tradeoffs ready for the README.

### Phase 4: Invites
- Group invite link and QR: seven-day multi-use links, admin revocation
- Signup-then-auto-join flow
- Exit: a new person joins a group from a link without admin action.

Implemented on 2026-10-30 (phases 3 and 4):
- Exact memoized minimum-transfer search, deterministic integer-paise output,
  cycle cancellation, and a display-only SSR/JSON suggestions view.
- Admin invite management, locally generated SVG QR, seven-day multi-use links,
  revocation, minimal public preview, and CSRF-protected joins.
- Explicit invite acceptance resumes after signup/login. Joining rechecks validity
  under the group lock; existing memberships are idempotent.
- Owner-requested privacy change: removed `/users`, its signup alias and People
  navigation. Add-member UI uses an exact username, without a platform directory.
- Atomic repeatable seed command creates five dummy accounts and sample expenses.
- 78 tests pass locally and in Docker on disposable PostgreSQL; Django and migration consistency checks pass.
- Invite migration applied to Neon; five dummy users and sample ledger seeded.
  Balance integrity passes. Rebuilt local Docker app is healthy; `/users` returns 404.

### Phase 5: Receipt OCR
- Image upload, preprocessing, Tesseract extraction of items, tax, total
- Review/correct screen (required, because Tesseract is imperfect)
- Per-item assignment to members; tax, service, tip and discounts split equally among people with items (owner confirmed on 2026-10-30)
- Creates an expense with per-user splits
- Exit: a real receipt photo becomes a correct expense after review.

Implemented on 2026-10-30:
- Bounded in-memory JPEG/PNG/WebP upload, orientation/grayscale/contrast preprocessing,
  Tesseract stdin/stdout extraction with timeout, and stateless editable drafts.
- Required explicit approval; equal-bill and itemised splits, shared/unassigned items,
  equal charges among item recipients, deterministic paise rounding and negative discounts.
- Receipt item/payee models, atomic saves/edits/deletion, audit snapshots and extended
  receipt/ledger integrity checks. The uploader is always the receipt payer.
- 91 tests pass in Docker, including actual Tesseract on an in-memory generated receipt;
  local suite passes with the binary-dependent test skipped. Checks and migration
  consistency pass. No real receipt photo was supplied; that exit trial remains pending.
- Browser automation host was unavailable at implementation time. Follow-up native
  browser mobile review is now complete; see `docs/UI_AUDIT.md` for coverage.
- Receipt migration applied to the configured Neon database; balance integrity passes.
  Local Docker app rebuilt and restarted; `/health` returns 200 and container is healthy.
- Receipt-parser follow-up: accept whole-rupee prices and currency suffixes, exclude
  common receipt metadata, and show explicit empty-extraction/total-mismatch warnings.
  The user's pasted OCR text is now covered by a regression test: noisy quantity/rate/
  total columns and border artifacts produce three items totalling INR 290.00.
  The original image attachment was unavailable, so image-level verification remains pending.

### Phase 6: Voice logging
- Browser mic recording, upload, Sarvam transcription
- Parse transcript into amount, description, payer, participants
- Approval screen; nothing is saved until the user confirms
- Exit: a spoken sentence becomes a draft expense that the user approves or edits.

Implemented on 2026-10-30:
- Browser microphone recording, 30-second auto-stop and in-browser WAV conversion;
  bounded, validated audio remains in memory throughout the application.
- Sarvam saaras:v3 codemix transcription with comma-separated SARVAM_API_KEYS in order.
  Owner confirmed fallback includes rate limits, invalid/exhausted credentials,
  provider failures and transport errors; bad audio is not retried across accounts.
- Both providers use comma-separated key strings, with ordered fallback including
  rate limits; Groq uses GROQ_API_KEYS. Empty entries and whitespace are ignored.
- Groq GPT-OSS 20B strict structured output via OpenAI SDK, with server validation
  of exact money/member IDs and warnings for ambiguous participants or payer.
- Editable transcript and expense review, explicit approval, atomic source=voice
  expense creation, and existing creator-only edit/delete and audit behavior.
- 106 tests pass in Docker; local suite passes with the Tesseract-dependent test skipped. Includes provider
  fallback, audio limits, strict parsing, membership/CSRF, draft non-persistence,
  explicit approval, corrections and balance integrity through edit/delete.
- Voice-source migration applied to the configured Neon database; balance integrity passes.
  Rebuilt local Docker app is healthy and `/health` returns 200.
- Owner reported the live voice logging trial works after trying the feature.
  Browser host unavailable; native browser access was stopped by the automation
  URL-policy check at implementation time. Follow-up native browser mobile review
  is now complete; see `docs/UI_AUDIT.md` for coverage and remaining device trials.
- Comma-separated provider configuration and Groq fallback follow-up: all 10
  provider tests pass, including blank entries, key order and rate-limit fallback.
- Provider API/schema/limits verified against official documentation. Actual
  Sarvam free-credit eligibility and account quotas remain console-specific.

### Phase 7: Insights
- Monthly summary and spend analytics (by category and by month)
- CSV export
- Settle-up nudges (pre-filled share text)

Implemented on 2026-10-30:
- Membership-protected SSR/JSON insights with selected-month group spend/count,
  caller paid/share totals, category breakdown (including Uncategorised), and
  twelve months of totals with zero-spend months included. Uses expense dates,
  exact paise, active expenses only; settlements do not alter spending.
- Streaming UTF-8 CSV for a selected month or all dates, one row per expense,
  named participant splits, caller share, stable ordering and spreadsheet formula
  protection. No emails or global user directory are exported.
- Copyable reminder text and supported-device share controls for actual direct
  debts owed to the caller, excluding pending claims. No messages are sent.
  Read responses disable caching; Phase 7 adds no schema migration/provider.
- 117 tests pass in Docker, including actual Tesseract; the local 116-test run
  passed with one binary-dependent skip before adding the page-audit test. All
  eight insights/audit tests pass locally. Django checks, migration consistency,
  and configured-database balance integrity pass. The rebuilt app is healthy.
- Seven Phase 7 business/endpoint tests plus a 21-page SSR structure audit cover
  report totals, rounding, dates, edits/deletes, settlements, group isolation,
  membership, validation, CSV quoting/formulas and pending-payment reminders.
- Full UI source inventory, component baseline, priorities and reference-led
  redesign acceptance matrix are in `docs/UI_AUDIT.md`. Native desktop review
  covered expense detail, dashboard and insights. The owner stopped the initial
  review, then explicitly requested the remaining mobile checks. Native responsive
  review now covers all 21 page states at 320px or 390px; the audit records each
  page's coverage. Fixed and visually rechecked a flex-row amount-wrapping defect.
  Physical-device and full transaction-flow acceptance remain separate work.
- Audit finding: role changes, member removal/leaving and group deletion are
  locked decisions identified as an implementation gap, now addressed by the
  group lifecycle follow-up below.

### Phase 8: Delivery
- README: setup, architecture, schema explanation, assumptions, design decisions, future improvements
- API documentation, optional Postman collection and demo video

## Open items (not yet decided)
1. **Sarvam live trial:** verify account free-credit eligibility and actual quotas. Owner reports the live voice flow works. Endpoint, 30-second limit, codemix mode and fallback conditions are resolved in Phase 6.
2. **Groq live trial:** continue assessing extraction quality; owner reports the live voice flow works. GPT-OSS 20B uses strict structured output; no executable tool calls are needed for drafts. Published free-tier limits are documented in README.
3. **Keep-alive:** the pinger must be external, since Render only counts incoming requests. Neon is on a Pro plan, so cold starts are not a concern; I'll still enable Django connection health checks.
4. **Schema:** no open questions left. See `SCHEMA.md` section 6.


### Approved application design rollout (2026-10-30)

Owner selected `docs/prototypes/index.html` and authorized applying its visual
system throughout the existing application with desktop layouts. Implemented a
shared responsive shell, local prototype typefaces/assets, group dashboard and
workspace, amount-first expense entry/edit/voice forms, checkbox split previews,
and consistent styles across all existing page surfaces. No schema changes or
new domain workflows. Validation and visual-review coverage are recorded in
`docs/UI_AUDIT.md` under Approved prototype rollout.


UI follow-up: completed secondary-page layouts, SVG navigation, contextual Add /
Activity links, account controls, report charts and receipt allocation chips.
Validated with 120 passing Docker tests and code-only DOM/interaction checks.
The owner prohibits computer/browser control; no further UI automation was used.
See the secondary-page completion section in `docs/UI_AUDIT.md` for limits.

### Group lifecycle follow-up (2026-10-31)

Resumed implementation at audit finding F1. Added admin role changes, removal
of members/admins, self-service departure and soft group deletion using the
existing schema. Every operation locks the group inside its transaction and
records an activity event. Removal/leaving requires every affected pairwise
balance to be zero; deletion requires every group balance to be zero. The last
admin cannot leave or be demoted. Rejoining restores the membership as a member.
Controls live on the Members page, with explicit leave/delete confirmation.

Owner resolved the historical-expense edge case on 2026-10-31: block edits or
deletion if they would recreate a balance for someone who has left. Such changes
roll back completely; the person can be invited to rejoin before making them.
No migrations are needed. Browser/computer control remains prohibited.

Verification: final Docker image passes all 134 tests against disposable
PostgreSQL, including actual Tesseract, the page audit, transaction rollback,
simultaneous admin departures, removal versus expense creation and invitation
joining versus group deletion. Container HTTP tests use
`DJANGO_SECURE_SSL_REDIRECT=False`; the first run without it had four existing
voice-workflow failures from 301 redirects. The earlier local 132-test run passed
with one expected Tesseract skip, before the final two endpoint/regression tests
were added. Migration consistency, asset collection and whitespace checks pass.
No shared database writes, browser/computer control or Git publication occurred.
