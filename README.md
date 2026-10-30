# BroYouOweMe

An INR expense-sharing service built with Django server-rendered templates,
plain CSS/JavaScript, and PostgreSQL on Neon. Phase 0 provides the project
foundation; accounts, groups, expenses, and balances arrive in later phases.

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
python manage.py check
python manage.py test
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. `GET /health` runs `SELECT 1` and returns
`{"status":"ok"}` (200) or `{"status":"unavailable"}` (503), without exposing
connection details. It works before application tables exist.
The unit tests require PostgreSQL configuration but do not connect to a
database; a real `/health` request verifies the configured database connection.

**Do not run migrations yet.** The custom user model and its initial migration
are Phase 1 work. Applying built-in auth migrations now would make switching
to that model harder. No domain models or auth endpoints exist in Phase 0.

## Docker

Start Docker Desktop with Linux containers, configure `.env`, then run:

```powershell
docker compose up --build -d
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
`DJANGO_DEBUG` defaults to false. `DB_CONN_MAX_AGE` defaults to zero; connection
health checks are enabled, connection attempts time out after five seconds,
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
IDs will be bigint, and timestamps use UTC. Domain tables, ledger transactions,
permissions, authentication, OCR, voice and deployment remain future work.

Configuration references: [Django PostgreSQL documentation](https://docs.djangoproject.com/en/5.2/ref/databases/),
[custom user migration guidance](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#changing-to-a-custom-user-model-mid-project),
and [WhiteNoise setup](https://whitenoise.readthedocs.io/en/stable/django.html).
