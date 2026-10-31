# Submission validation

Original submission checks ran on 31 October 2026 against commit `011b822`. The Render preparation checks below include the subsequent changes for reviewer seeding and Render HTTPS configuration. Public deployment remains unverified.

## Render preparation checks

| Check | Result |
|---|---|
| Current Django suite | 140 tests ran successfully; one native Tesseract test skipped |
| Reviewer demo tests | Six passed: logins/starting balances, repeat seed after payment, collision rollback, missing password, changed password, original dummy seed |
| Docker build | Passed, including static collection |
| Blueprint startup command | Ran verbatim in local Docker against a new disposable PostgreSQL database; migrations, reviewer seed and Gunicorn succeeded |
| Production-style HTTP checks | `/health` returned 200; all three CSRF-protected reviewer logins and seeded group requests passed with Render hostname/forwarded HTTPS headers |
| Static stylesheet | Served successfully from collected Docker assets |
| Repeat seed and ledger integrity | Passed in Docker |
| Django system check / migration drift | No issues / no changes detected |
| Git whitespace check | Passed |
| Branding assets | PNG/ICO sizes and production static manifest verified; six foundation tests passed after favicon integration |

Tests used a separate disposable PostgreSQL 17 container. The existing submission container, configured project database and `.env` were not changed. The public Render deployment, its assigned hostname and a real external cron request remain unverified. Publish using [SETUP.md](SETUP.md#publish-on-render) and replace the live URL placeholders before submitting.

## Original submission results

| Check | Result |
|---|---|
| Clean PostgreSQL migrations | Passed |
| Django system check | No issues |
| Django test suite | 134 tests ran; passed with one skipped |
| Actual Tesseract image extraction | Passed separately in Docker |
| Postman through Newman | 46 requests, 59 assertions, zero failures |
| Repeated Postman run with supplied environment | 46 requests, 59 assertions, zero failures |
| Ledger integrity after demo and collection runs | Passed |
| Migration drift check | No changes detected |
| Git whitespace check | Passed |

The native suite skipped the actual Tesseract binary test because Tesseract is not installed on the Windows PATH. That exact test passed in the project's Docker image, using the current source mounted read-only. Other receipt tests ran in the native suite.

The tests and demo used a fresh disposable PostgreSQL 17 container. The configured project database and `.env` were not modified. The demo used local dummy accounts; Postman generated unique accounts for each run.

## Commands used

```powershell
python manage.py migrate --noinput
python manage.py check
python manage.py test --noinput
python manage.py check_balances
python manage.py makemigrations --check --dry-run
npx --yes newman run BroYouOweMe.postman_collection.json --folder "01 Automated submission flow" --environment BroYouOweMe.local.postman_environment.json --bail
git diff --check
```

`DATABASE_URL` was overridden for these commands to select the isolated database. See [SETUP.md](SETUP.md) for a disposable test database setup.

## Coverage limits

The manual Postman examples are supplied for individual use with their stated prerequisites. They were not run as an automated folder. Provider-backed voice transcription and parsing were not called during this submission check. The video shows receipt and voice review screens, with no claim of a live provider demonstration. Public app hosting and playback of the supplied unlisted YouTube link were not tested.

GitHub's `main` branch was reachable and matched local commit `011b822` before the submission changes were prepared. The public app URL still needs to be filled in after deployment.
