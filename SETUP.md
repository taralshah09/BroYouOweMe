# Setup instructions

## Requirements

- Python 3.13 and Git.
- PostgreSQL. A Neon connection string or a local instance works.
- Docker Desktop with Linux containers if using Docker.
- Tesseract with English language data for native receipt OCR. The Docker image includes it.

Commands below use PowerShell from the repository root. On macOS or Linux, use `source .venv/bin/activate` and `cp` instead of the Windows activation and copy commands.

## Install dependencies

```powershell
git clone https://github.com/taralshah09/BroYouOweMe.git
cd BroYouOweMe
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If activation is blocked, use `.venv\Scripts\python.exe` instead of `python`.

## Set the environment

Copy the example only if `.env` does not already exist:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Edit `.env` with these local values. Replace both placeholders:

```dotenv
DJANGO_SECRET_KEY=<generated-secret>
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
DATABASE_URL=<postgresql-connection-string>
DB_CONN_MAX_AGE=60
DJANGO_SECURE_SSL_REDIRECT=false
PORT=8000
SARVAM_API_KEYS=
GROQ_API_KEYS=
```

Use the complete Neon connection string, including `sslmode=require`, if using Neon. There is no SQLite fallback. Existing environment variables override `.env`. Keep real credentials out of Git and Postman exports.

For a local database with Docker:

```powershell
docker run --detach --name byom-local-db -e POSTGRES_PASSWORD=local-dev-only -e POSTGRES_DB=byom -p 127.0.0.1:55432:5432 postgres:17-alpine
docker exec byom-local-db pg_isready -U postgres
```

Wait for `accepting connections`, then use `postgresql://postgres:local-dev-only@127.0.0.1:55432/byom` as `DATABASE_URL`. This password is for local development only. Stop and start this container with `docker stop byom-local-db` and `docker start byom-local-db`.

## Create tables and start

```powershell
python manage.py migrate
python manage.py check
python manage.py check_balances
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and register through `/signup`. `/health` returns `{"status":"ok"}` when PostgreSQL is reachable. It checks the connection, not whether migrations have run.

Create three accounts in separate browser sessions, or use the Postman runner. As the group admin, add the other accounts by exact username. Record INR 1,200 paid by the first account. The other two should each owe that person INR 400.

Optional: `python manage.py seed_demo` creates five dummy users and a sample group. Dummy accounts have unusable passwords and cannot log in. Register your own account and add `demo_mohit`, `demo_rahul`, `demo_ankit`, `demo_priya` or `demo_sneha` to a group you own to try splits. The command is repeatable and does not overwrite identities or passwords.

## Docker app

Configure `.env` first:

```powershell
docker compose up --build -d
docker compose run --rm web python manage.py migrate
docker compose ps
curl.exe --fail http://127.0.0.1:8000/health
docker compose exec web tesseract --version
```

Compose uses `DATABASE_URL` and does not create PostgreSQL. If PostgreSQL runs through a published host port, use `host.docker.internal:55432` in the web container's URL. `127.0.0.1` inside the web container points to the web container itself.

The image runs Gunicorn as an unprivileged user and serves collected assets through WhiteNoise. Migrations are explicit. Stop the app with `docker compose down`.

## Receipt and voice setup

Native receipt OCR needs `tesseract --version` to work in the shell that starts Django. Upload JPEG, PNG or WebP, up to 8 MiB and 20 megapixels. Correct extracted items and approve before saving. Manual receipt entry remains available if OCR is unavailable.

Set `SARVAM_API_KEYS` and `GROQ_API_KEYS` to enable audio transcription and voice parsing. Each accepts one key or a comma-separated list. Restart Django after changing them. For Docker, use `docker compose up -d --force-recreate`. Typed transcripts need Groq; audio needs both providers. Core expenses and settlements need neither.

Microphone recording needs localhost or HTTPS and a supported browser. The browser sends mono 16 kHz, 16-bit PCM WAV, up to 30 seconds and 2 MiB. Review and approve before saving.

## Run the tests

Use a separate disposable PostgreSQL instance. Django creates a test database and needs a role with `CREATEDB`. Do not use shared or production data.

```powershell
docker run --detach --rm --name byom-tests -e POSTGRES_PASSWORD=local-test-only -e POSTGRES_DB=byom -p 127.0.0.1:55433:5432 postgres:17-alpine
docker exec byom-tests pg_isready -U postgres
$env:DATABASE_URL='postgresql://postgres:local-test-only@127.0.0.1:55433/byom'
python manage.py test --noinput
Remove-Item Env:DATABASE_URL
docker stop byom-tests
```

Wait for database readiness first. Remove the override even if tests fail so later commands use `.env` again. After trying the app, run `python manage.py check_balances` against that app's database.

## Deployment settings

For HTTPS hosting, use `DJANGO_DEBUG=false`, explicit allowed hosts, trusted HTTPS origins, and `DJANGO_SECURE_SSL_REDIRECT=true`. Secure session and CSRF cookies are enabled when debug is off. Use `DB_CONN_MAX_AGE=0` for ASGI. Set credentials in the host's environment. The Docker image excludes `.env` and Git history.

## Publish on Render

The repository includes [render.yaml](render.yaml): a Free Docker web service using the existing image (including Tesseract), Gunicorn, WhiteNoise and external Neon PostgreSQL. Deployment is not yet verified on a live Render service; the final URL must be copied from your Render dashboard.

1. Prepare a **dedicated Neon database or branch for the public demo**, with a PostgreSQL connection string including `sslmode=require`. Reviewer accounts share editable data; use a database containing only dummy data.
2. Commit and push the prepared files to `taralshah09/BroYouOweMe` after reviewing them. Render builds from GitHub, so local changes are unavailable until pushed. Never include `.env`. This guide does not execute Git operations.
3. Open the [Render dashboard](https://dashboard.render.com/), choose **New > Blueprint**, connect that repository, select the branch containing `render.yaml`, and review the Free web service.
4. Supply the prompted environment variables:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Dedicated Neon demo connection string, with SSL enabled |
   | `DEMO_PASSWORD` | `BroYouOweMeDemo2026!` (public demo password documented for reviewers) |

   The Blueprint generates `DJANGO_SECRET_KEY` and configures debug off, HTTPS redirection and `/health`. The app reads Render's assigned hostname for allowed hosts and CSRF origins, and recognizes HTTPS forwarded by Render. No wildcard host setting is required.
5. Deploy the Blueprint. The Docker build installs dependencies, Tesseract and collected static files. Its startup override runs migrations, then `seed_demo --reviewer`, then Gunicorn. Startup seeding works on the Free plan without requiring a dashboard shell or pre-deploy hook.
6. Copy the **actual assigned URL** from Render (the requested name is `broyouoweme`, but Render may assign a suffix). Open `/health`, then `/login`. Sign in with the accounts in [DEMO.md](DEMO.md#try-the-hosted-demo). Check the seeded group, styles and an expense/payment interaction.
7. Replace `<render-app-url>` in [SUBMISSION.md](SUBMISSION.md) and [DEMO.md](DEMO.md) with that exact HTTPS base URL before submitting. Include both the live URL and the demo credentials in the submission form.

For optional voice features, add `SARVAM_API_KEYS` and `GROQ_API_KEYS` in the service's Environment page and redeploy. OCR is included in the image; core expense and settlement flows need no provider keys. If using a custom domain, also set `DJANGO_ALLOWED_HOSTS` to that hostname and `DJANGO_CSRF_TRUSTED_ORIGINS` to its full HTTPS origin.

### If you choose New > Web Service instead of Blueprint

Connect the same repository, choose **Docker** with the root `Dockerfile`, and select the **Free** instance. A manually created Web Service does not read `render.yaml` automatically. Set **Health Check Path** to `/health` and add these environment variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Full Neon PostgreSQL URL, preserving its SSL query parameters; paste the URL only, without `psql` or surrounding quotes |
| `DJANGO_SECRET_KEY` | A new random secret generated for the hosted app |
| `DEMO_PASSWORD` | `BroYouOweMeDemo2026!` |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECURE_SSL_REDIRECT` | `true` |
| `DB_CONN_MAX_AGE` | `60` |

The same Neon URL as local development works, but both apps then share every account, group, expense and payment. For public reviewer access, prefer a dedicated empty demo database. A Neon branch copied from an existing branch also copies its existing data, so do not assume branching removes personal data.

Set **Docker Command** to the following startup override so migrations and reviewer seeding run before serving requests:

```sh
sh -c 'python manage.py migrate --noinput && python manage.py seed_demo --reviewer && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 --access-logfile - --error-logfile -'
```

Render supplies `RENDER` and `RENDER_EXTERNAL_HOSTNAME` automatically. For the generated Render hostname, leave `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` unset; the app adds the exact hostname and HTTPS origin itself.

The startup command preserves existing demo data and passwords. It does not reset payment confirmations or duplicate the dinner on each restart. Keep `DEMO_PASSWORD` consistent; if an existing reviewer identity has a different password or unexpected privileges, startup stops rather than replacing it. To reproduce the initial walkthrough after public edits, create a fresh three-person group and dinner, or deploy against a fresh dedicated demo database. `python manage.py seed_demo` without `--reviewer` retains the original five non-login dummy users.

To seed a local or separately managed demo database yourself:

```powershell
$env:DEMO_PASSWORD='BroYouOweMeDemo2026!'
python manage.py migrate --noinput
python manage.py seed_demo --reviewer
python manage.py check_balances
Remove-Item Env:DEMO_PASSWORD
```

### Health URL and external cron

Use **`<render-app-url>/health`**, without a trailing slash, with an unauthenticated **GET** request. For example, **only if Render assigns this exact hostname**, the URL is `https://broyouoweme.onrender.com/health`. A healthy app and database return HTTP 200 with `{"status":"ok"}`; an unavailable database returns HTTP 503. Responses are not cached. This endpoint checks database connectivity, not migration completeness.

Configure your existing external cron to request the URL every **10 minutes** (`*/10 * * * *`). A 15-minute schedule (`*/15 * * * *`) sits exactly at Render's idle threshold and can race with spin-down. Example for a Linux cron host, replacing the hostname:

```cron
*/10 * * * * curl --fail --silent --show-error --max-time 90 https://YOUR-ASSIGNED-HOST.onrender.com/health
```

Use GET rather than HEAD because the endpoint accepts GET only. Allow up to 90 seconds for a cold start. A keep-alive request reduces idle gaps but does not guarantee uptime: free services remain subject to restarts and free usage limits. See Render's [Free service limits](https://render.com/docs/free) and [health checks](https://render.com/docs/health-checks). For guaranteed absence of idle spin-down, choose a paid instance.

Render's official references: [Blueprint configuration](https://render.com/docs/blueprint-spec), [default Render environment variables](https://render.com/docs/environment-variables), and [deploy lifecycle](https://render.com/docs/deploys).

## Troubleshooting

| Problem | Check |
|---|---|
| Missing secret or database setting | Fill `.env`; check for an overriding shell variable. |
| Database connection fails | Check host, port, credentials, network access and SSL parameters. |
| Missing tables | Run migrations against the database used by the app. |
| Local HTTP redirects to HTTPS | Set debug true and SSL redirect false, then restart. |
| POST returns 403 | Preserve cookies and send the current CSRF token. See [POSTMAN.md](POSTMAN.md). |
| Docker cannot reach PostgreSQL | Use `host.docker.internal` for a database exposed on the host. |
| OCR fails | Check Tesseract and English data, or enter the receipt manually. |
| Voice returns 503 | Check provider keys, connectivity and account limits. |
