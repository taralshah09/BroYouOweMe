# BroYouOweMe

An INR expense-sharing service built with Django server-rendered templates,
plain CSS/JavaScript, and PostgreSQL on Neon. Phase 1 includes session auth,
groups, equal-split expenses, and maintained pairwise balances.

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
Uploaded files use only the in-memory upload handler; OCR and voice processing
and their input limits will be added in their planned phases.

The schema and later work are documented in [docs/SCHEMA.md](docs/SCHEMA.md)
and [docs/PLAN.md](docs/PLAN.md). Money is stored as integer paise, all domain
IDs are bigint, and timestamps use UTC. Split rows, settlements, categories,
OCR, voice, invites, insights, and production deployment remain future work.

Configuration references: [Django PostgreSQL documentation](https://docs.djangoproject.com/en/5.2/ref/databases/),
[custom user migration guidance](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#changing-to-a-custom-user-model-mid-project),
and [WhiteNoise setup](https://whitenoise.readthedocs.io/en/stable/django.html).


## Phase 1 behavior

Open `/signup` to create an account. Create a group at `/groups`, add registered
users as its admin, and record an expense from the group page. All current
members share it equally, including the payer. Only other members create debts.
Any active member may record a payment made by another active member.

Membership additions and expense creation both lock the group row. Phase 1
membership is append-only: the members whose `joined_at` precedes an expense's
`created_at` are its participants. Adding a friend later never changes earlier
expenses, even when an expense is backdated. Phase 2 replaces this calculation
with explicit split rows before expense edits or membership changes are enabled.
Amounts below one paisa per participant are rejected so every share is positive.

The balances table stores one signed value per unordered user pair per group.
Opposite debts net automatically; unrelated pairs are not simplified. Expense
and balance writes commit together or roll back together. Run
`python manage.py check_balances` to recompute expense history under group locks
and detect drift without changing any balances.

`/balances` combines only the logged-in user's pairs across their active groups.
`/groups/{id}/balances` shows every nonzero pair in a group they belong to.
All group reads check active membership; adding members requires the admin role.
User listings expose IDs and usernames, never emails or password hashes.
Usernames are at most 32 characters; `@` is reserved for email login.

See [API documentation](docs/API.md) for endpoints, CSRF, and exact money formats.
The future schema is documented in [SCHEMA.md](docs/SCHEMA.md); categories,
settlements, edits, deletions, invites, OCR, and voice remain later-phase work.

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
The suite covers the exact Mohit/Rahul/Ankit dinner example, integer rounding,
netting, rollback after a partial balance update, concurrent creation, historical
membership, input validation, database constraints, auth, CSRF, and SSR routes.


## Product enhancement: private, authenticated groups

Session authentication and group admin permissions add privacy to the assignment's
shared-expense API: users see only their own groups, and group membership is
controlled by an admin. This prevents a guessed group ID from exposing a trip's
expenses or letting an outsider add debts. Django sessions keep login simple for
SSR pages and work with CSRF protection. The tradeoff is that every participant
must register; email verification and guest participants are outside this plan.
