# BroYouOweMe

An INR expense-sharing service built with Django server-rendered templates,
plain CSS/JavaScript, and PostgreSQL on Neon. Phases 1-7 include spending insights, CSV export, shareable payment reminders, voice drafts, receipt OCR with review, private session auth, invite links/QR codes, minimum-transfer suggestions, groups, equal/subset/unequal expenses, creator-only
edits and soft deletion, confirmed settlements, categories, and an activity feed.

## Local setup

Use Python 3.13 and PostgreSQL (Neon for the project database).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

If `.env` already exists, keep it. Paste the generated key into
`DJANGO_SECRET_KEY`. Set `DJANGO_DEBUG=true`,
`DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]`, and
`DJANGO_SECURE_SSL_REDIRECT=false` for local HTTP development.
Set `DATABASE_URL` to the connection string from Neon's Connect dialog,
including its `sslmode=require` parameter. Keep credentials only in `.env`
or the host's environment. Environment variables take precedence over `.env`.
`.env.example` intentionally contains variable names with empty values only.

```powershell
python manage.py migrate
python manage.py check
python manage.py check_balances
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. `GET /health` runs `SELECT 1` and returns
`{"status":"ok"}` (200) or `{"status":"unavailable"}` (503), without exposing
connection details. It works before application tables exist.
The test suite uses real PostgreSQL, including transaction and concurrency tests.
Use a disposable local database as described below; a real `/health` request
verifies the configured database connection.

The custom user model and initial migrations are now included. Run `migrate`
before signing up. Signup creates a session; login accepts an email or username
(case-insensitive). Passwords use Django hashing and validation.

## Group management

Group admins can manage roles and remove members from **Members**. Members can
leave after settling every pairwise balance; the last admin must promote someone
first. Admins can delete a group only after every balance is zero. Deletion hides
the group and its invitations while retaining its history. Expense changes that
would recreate a balance for a departed member are blocked; invite them to rejoin
before making those changes. These actions are also documented in `docs/API.md`.

## Docker

Start Docker Desktop with Linux containers, configure `.env`, then run:

```powershell
docker compose up --build -d
docker compose run --rm web python manage.py migrate
docker compose ps
curl.exe --fail http://127.0.0.1:8000/health
docker compose exec web tesseract --version
docker compose down
```

Compose connects to the database in `DATABASE_URL`; it does not create a
second database. The image includes Tesseract, serves collected static assets
through WhiteNoise, and runs Gunicorn as an unprivileged user. The image copies
only application files, excluding `.env`, Git history and the assignment.
Migrations never run automatically. `PORT` defaults to 8000; Compose fixes it
to 8000 to match its loopback-only published port.

## Configuration and architecture

- `config/`: settings, root URLs, WSGI and ASGI entry points.
- `apps/`: accounts, groups, expenses, settlements, activity, insights and AI.
  Business logic belongs in each app's `services` module; tests live in its
  `tests/` folder. The operations health probe currently lives in accounts.
- `templates/` and `static/css/`, `static/js/`: server-rendered frontend.
- `apps/expenses/services/money.py`: exact rupee conversion, two-decimal
  formatting and equal allocation. Floats and excess precision are rejected;
  remainder paise go to ascending user IDs. Negative allocation supports
  discounts; zero shares are retained for later expense validation.

Settings require a secret key and PostgreSQL URL, with no SQLite fallback.
`DJANGO_DEBUG` defaults to false. `DB_CONN_MAX_AGE` defaults to 60 seconds, so
each WSGI worker reuses its database connection across requests. Set it to `0`
to disable reuse. Connection health checks are enabled before reuse;
connection attempts time out after five seconds,
and server-side cursors are disabled for Neon pooled connections.
Use `DB_CONN_MAX_AGE=0` when running ASGI.
`DJANGO_CSRF_TRUSTED_ORIGINS` accepts comma-separated origins including schemes.
For deployment, set explicit allowed hosts and trusted HTTPS origins, keep
debug disabled, and configure HTTPS at the host. HTTPS redirect defaults on;
the minimal health endpoint is exempt so container HTTP probes work.
Receipt uploads use a bounded in-memory upload handler. OCR has byte, pixel and
execution-time limits. Voice recordings are bounded WAV uploads processed in memory.

The schema and later work are documented in [docs/SCHEMA.md](docs/SCHEMA.md)
and [docs/PLAN.md](docs/PLAN.md). Money is stored as integer paise, all domain
IDs are bigint, and timestamps use UTC. Production delivery remains Phase 8 work.

Configuration references: [Django PostgreSQL documentation](https://docs.djangoproject.com/en/5.2/ref/databases/),
[custom user migration guidance](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#changing-to-a-custom-user-model-mid-project),
and [WhiteNoise setup](https://whitenoise.readthedocs.io/en/stable/django.html).


## Phase 2 behavior

Open `/signup` to create an account. Create a group at `/groups`, add registered
users as its admin, and record an expense from the group page. Choose equal shares
among all members or a subset, or enter exact amounts per participant. The payer
may be any active member and need not be a participant. Every share is positive
and stored as integer paise; shares always sum to the total. Remainder paise go to
ascending user IDs. Adding members never changes historical splits.

The expense creator can edit or delete from its detail page. Edits reverse old
allocations and apply new ones atomically; deletion keeps an audit record and
reverses the expense's debts. Pending and confirmed settlements remain in history.
A correction after settlement may reverse who owes whom.

Use **Settle up** to claim a partial or full payment toward a real pairwise debt.
Only the receiver can confirm or reject, and the payer can cancel a pending claim.
Balances change on confirmation only. Pending claims reserve the current debt;
overpayment is checked both when claimed and when confirmed, under the group lock.

Any member can manage group categories. The seven built-in categories are shared
and immutable; custom names are unique within their group and cannot duplicate
default names. Used categories can be renamed but cannot be deleted, even when
only a soft-deleted expense uses them. Expenses also accept an optional tag.

The group dashboard links to **Activity**, a paginated feed with before/after
expense changes, settlement transitions, and category changes. Audit events and
ledger writes commit or roll back together. All group reads require membership.

Balances store one signed value per unordered user pair per group. Opposite debts
net automatically; unrelated pairs are not simplified. `/balances` combines only
the logged-in user's pairs across active groups. Run `python manage.py check_balances`
to verify split totals and recompute active expenses minus confirmed settlements
under group locks without changing maintained balances.

For an existing Phase 1 database, stop old workers, run `python manage.py migrate`,
and start the Phase 2 app. The data migration uses original membership join times
to preserve historical equal splits, creates matching historical activity events,
and leaves balances intact. The transition is intentionally irreversible; old
workers must not write expenses after migration.

See [API documentation](docs/API.md) for endpoints, CSRF, split payloads, filtering,
and exact money formats, and [SCHEMA.md](docs/SCHEMA.md) for ledger invariants.

## Testing against disposable PostgreSQL

Do not point automated tests at a shared database. Django creates and drops a
separate `test_<database name>` database and requires a role with `CREATEDB`.
For a local disposable database (this password is for the test container only):

```powershell
docker run --detach --rm --name byom-tests -e POSTGRES_PASSWORD=local-test-only -e POSTGRES_DB=byom -p 127.0.0.1:55432:5432 postgres:17-alpine
docker exec byom-tests pg_isready -U postgres
$env:DATABASE_URL='postgresql://postgres:local-test-only@127.0.0.1:55432/byom'
python manage.py test --noinput
Remove-Item Env:DATABASE_URL
docker stop byom-tests
```

Wait until `pg_isready` reports accepting connections before running tests.
The suite covers the exact assignment scenario, deterministic allocation,
unequal/subset splits, edit/delete rollback and audit snapshots, category scope,
settlement reservations and confirmation, concurrent creation/claims/confirmations,
historical split migration, integrity drift, auth, CSRF, and SSR workflows.


## Product enhancement: private, authenticated groups

Session authentication and group admin permissions add privacy to the assignment's
shared-expense API: users see only their own groups, and group membership is
controlled by an admin. This prevents a guessed group ID from exposing a trip's
expenses or letting an outsider add debts. Django sessions keep login simple for
SSR pages and work with CSRF protection. The tradeoff is that every participant
must register; email verification and guest participants are outside this plan.


## Debt simplification and invites

Suggested settlements aggregates net group balances and finds the exact minimum
number of transfers in integer paise. The search exhausts a debtor or creditor at
each match, memoizes residual states, prunes equivalent balances and stops early
at the debtor/creditor count lower bound. Stable user-ID order makes ties deterministic.
Cycles cancel naturally. Exact search has exponential worst-case cost and is intended
for small shared-expense groups; greedy largest-first matching is faster but cannot
guarantee the minimum. Suggestions are display only: claims still require real
pairwise debts and no ledger entries are rewritten.

Admins manage invite links and locally generated QR codes from the group page.
Links last seven days, support multiple joins, and can be revoked. A visitor accepts
the link, signs up or logs in, and joins automatically. Preview exposes only group
name and member count. Expired/revoked links never grant membership.

The People page and `/users` API, including the signup alias, are removed for privacy.
Register through `/signup`; admins add friends by exact username or share an invite.

## Dummy data

Run `python manage.py seed_demo` after migrations. It creates `demo_mohit`,
`demo_rahul`, `demo_ankit`, `demo_priya`, and `demo_sneha`, plus Demo Goa Trip with
three sample expenses. Accounts use reserved `example.invalid` addresses and unusable
passwords, so cannot log in. Add these exact usernames to a group you own to try splits.
Use a separate normal account to test login. The seed is atomic and repeatable,
never overwrites identities or passwords, and aborts on collisions. Sample ledger
writes go through normal services.


## Phase 5: Receipt OCR

Choose **Scan a receipt** on a group page. Upload JPEG, PNG or WebP, then correct
all extracted lines and the total, select participants, and assign item payees.
Use whole-bill equal splitting or itemised splitting. An unassigned item belongs
to all selected participants. Tax, service, tip and discounts are divided equally
among people with items, as confirmed by the owner. Discount lines are negative.
The uploader is always the payer. Lines must sum exactly to the reviewed total;
nonpositive final shares are rejected. Approve explicitly to save the expense.

Images and drafts are never stored. Pillow checks the decoded format, applies
EXIF orientation, grayscale and contrast preprocessing, then sends PNG bytes to
Tesseract through stdin; text returns through stdout without temporary images.
Limits: 8 MiB per upload, 20 megapixels, 25 seconds of OCR, and 100 reviewed lines.
The extractor recognizes lines ending in whole-rupee or one/two-decimal prices,
including currency labels before or after the amount; other layouts may
need corrections. Quantity/rate/total tables use the final line total, with common
border artifacts and item numbering removed. Other layouts may
need manual corrections. It does not infer missing prices, quantities or rounding
adjustments. Add or correct these lines before approval. The review page also
supports manual entry if recognition is unavailable.

Docker includes Tesseract. For native Windows development, install Tesseract with
English language data and add it to PATH. Install updated Python requirements and
run `python manage.py migrate` before running this version. Receipt edits use the
same review screen and preserve item history in activity snapshots; deletion
reverses balances while retaining the receipt rows. `check_balances` also verifies
receipt totals and allocations. Source constraints allow manual, OCR and voice expenses.

Implementation references: [Tesseract command line](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)
and [Pillow image handling](https://pillow.readthedocs.io/en/stable/reference/Image.html).


## Phase 6: Voice logging

Choose **Log by voice** on a group page. Record an English/Hinglish sentence
(up to 30 seconds), or type a transcript. Review the resulting amount,
description, payer and participants, correct them, check the approval box and
save. You can enter exact shares during review. No draft operation writes to the
ledger; approval uses the same locked, atomic expense service as manual entry.

Configure `SARVAM_API_KEYS` and `GROQ_API_KEYS` as comma-separated key strings in
`.env`, then recreate the container (`docker compose up -d --force-recreate`).
One key per provider is sufficient; whitespace and empty entries are ignored.
Both providers try configured keys in order. For example, use
`SARVAM_API_KEYS=key1,key2,key3` and `GROQ_API_KEYS=key1,key2`. Fallback includes
401/402/403, 429 rate limits, server errors and network failures. Invalid audio
is not retried across accounts. Keys never reach the browser. Account credits,
free-tier eligibility and actual limits must be checked in the provider consoles.

Microphone access requires HTTPS or localhost and MediaRecorder/Web Audio support.
The browser converts captured audio to mono 16 kHz, 16-bit PCM WAV. The server
validates WAV contents, byte size (2 MiB), complete frame data and duration before
calling Sarvam's synchronous `/speech-to-text` with `saaras:v3`, `codemix` and
automatic language detection. Audio never touches application disk or the database.
Transcripts and group usernames go to Groq through the OpenAI SDK using
`openai/gpt-oss-20b` and strict JSON schema output. No executable tools are exposed;
server validation checks money and member IDs again. Unknown members remain
unselected and warnings prompt correction. The app stores neither transcript nor
audio; providers have their own retention policies. Draft responses disable caching.

Groq's published free-plan table currently lists 30 requests/minute, 1,000/day,
8,000 tokens/minute and 200,000/day for both GPT-OSS sizes; 20B is used for this
small extraction task. Account limits may differ. Calls have explicit timeouts
and no SDK retries. Each provider stops starting fallback attempts after a
40-second budget; Gunicorn allows 120 seconds for both provider chains. A parser failure preserves the transcript for correction.
The owner reported a successful live voice logging trial. Follow-up native browser
review covered the mobile voice layout and all other page states; see the UI audit
for precise coverage and remaining physical-device interaction checks.

References: [Sarvam STT API](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe),
[Groq structured outputs](https://console.groq.com/docs/structured-outputs),
[Groq rate limits](https://console.groq.com/docs/rate-limits).

## Phase 7: Insights

Open **Insights & export** from a group. Select a month to see group spending,
expense count, your actual participant share, and how much you paid. Category
totals cover that month; the monthly list covers twelve months ending with the
selection, including zero-spend months. Reports use `expense_date`, exclude
soft-deleted expenses, and never treat settlements as spending. Missing categories
appear as Uncategorised. The default is the current month in the app's UTC timezone.
All totals use integer paise and exact two-decimal INR strings.

Download the selected month or all dates as UTF-8 CSV. Each active expense gets
one row with its date, description, category, tag, source, payer, total, your share
and named participant splits. Rows are ordered by expense date and ID. User text
that could execute as a spreadsheet formula is prefixed with an apostrophe.
CSV describes current expenses; settlement history and deleted expense versions
remain in the activity ledger.

**Payment reminders** provides copyable text for actual direct debts owed to you
in the selected group. Pending claims awaiting your confirmation are subtracted
so a payer is not chased for those amounts. A fully pending debt needs no reminder.
Refresh before sharing for the latest balance. Use Copy, manually select the
text, or use your device's Share feature when supported. Nothing is sent automatically.
Every report/export/reminder requires current group membership and disables caching.
Phase 7 needs no migration or new external provider.

The page inventory, component audit, gaps and redesign checklist are in
[docs/UI_AUDIT.md](docs/UI_AUDIT.md).
