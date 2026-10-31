<p align="center">
  <img src="static/branding/logo.png" alt="BroYouOweMe receipt buddy logo" width="140" />
</p>

<h1 align="center">BroYouOweMe</h1>

<p align="center">Split the bill. Keep the friendship.</p>

BroYouOweMe tracks shared expenses in INR. Create a group, add your friends, record who paid, and see who owes whom. A payment clears a debt only after the receiver confirms it.

Built with Python 3.13, Django 5.2, PostgreSQL, Django templates, plain CSS and JavaScript. The Docker image runs Gunicorn, serves static files through WhiteNoise, and includes Tesseract for receipt OCR.

## Submission links

| Item | Location |
|---|---|
| GitHub repository | [taralshah09/BroYouOweMe](https://github.com/taralshah09/BroYouOweMe) |
| Setup instructions | [SETUP.md](SETUP.md) |
| Deploy to Render | [Render deployment guide](SETUP.md#publish-on-render) and [render.yaml](render.yaml) |
| Try the seeded demo | [Reviewer logins and walkthrough](DEMO.md#try-the-hosted-demo) |
| API documentation | [API.md](API.md) |
| Database schema | [SCHEMA.md](SCHEMA.md) |
| Postman collection | [POSTMAN.md](POSTMAN.md) |
| Demo video | [Watch on YouTube](https://youtu.be/lcuZM38lUzQ) |
| Submission checklist | [SUBMISSION.md](SUBMISSION.md) |

## What it does

- Private groups with admin roles, invite links and QR codes.
- Equal splits, selected participants, exact unequal shares, and receipt item splits.
- Expense corrections and soft deletion with an activity history.
- Pairwise balances, partial payment claims, and receiver confirmation.
- Suggestions that find the minimum number of transfers for a small group.
- Receipt OCR with Tesseract and voice entry with Sarvam and Groq. Both require review before saving.
- Monthly insights, category totals, CSV export, and copyable payment reminders.

## Run locally

Install Python 3.13 and use a PostgreSQL database. From PowerShell:

```powershell
git clone https://github.com/taralshah09/BroYouOweMe.git
cd BroYouOweMe
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Keep an existing `.env`. Set the generated value as `DJANGO_SECRET_KEY`, add your PostgreSQL `DATABASE_URL`, and set `DJANGO_DEBUG=true` and `DJANGO_SECURE_SSL_REDIRECT=false` for local HTTP. Then run:

```powershell
python manage.py migrate
python manage.py check
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and create an account. Full environment settings, Docker instructions, optional providers and troubleshooting are in [SETUP.md](SETUP.md).

## The assignment example

Mohit, Rahul and Ankit are members of Goa Trip. Mohit pays INR 1,200 for dinner. Each person's share is INR 400, so Rahul owes Mohit INR 400 and Ankit owes Mohit INR 400.

```json
{"Rahul":{"owes":{"Mohit":400}},"Ankit":{"owes":{"Mohit":400}}}
```

The Postman runner repeats this flow with unique account names, checks the balances, creates a payment claim as Rahul, and confirms it as Mohit.

## How the ledger works

Money is stored as integer paise. INR 100 split between three people becomes 3,334, 3,333 and 3,333 paise. Leftover paise go to ascending user IDs. Historical splits do not change when someone joins later.

Each group has one signed balance row per unordered pair of users. Opposite debts cancel within that pair. Expense creation, edits, deletion and payment confirmation lock the group row and update the ledger in one database transaction. The activity event commits with the operation. `python manage.py check_balances` recomputes the ledger and checks stored balances.

Suggestions use exact search to minimize transfer count. They are display only. Payment claims still require a real direct debt between the payer and receiver.

## Project layout

| Path | Purpose |
|---|---|
| `config/` | Settings, routes, WSGI and ASGI |
| `apps/accounts/` | Registration, sessions and health check |
| `apps/groups/` | Groups, membership, roles and invites |
| `apps/expenses/` | Expenses, splits, categories and receipt items |
| `apps/settlements/` | Balances, claims and simplification |
| `apps/activity/` | Audit events and feed |
| `apps/ai/` | Receipt and voice draft processing |
| `apps/insights/` | Reports, CSV export and reminders |
| `templates/`, `static/` | Server-rendered interface and browser assets |
| Repository root | Setup, API, schema and submission files |
| `docs/` | Project plan, UI audit and design prototypes |

Business rules live in service modules. Views handle requests, permissions and responses.

## Checks

Use a disposable PostgreSQL database for tests. Commands are in [SETUP.md](SETUP.md#run-the-tests). The suite covers allocation, corrections, settlement reservations, concurrent writes, invitations, authentication, CSRF, receipt review, voice drafts, reporting and browser page responses.

## Decisions and limits

Groups are private and every participant needs an account. Only the expense creator can edit or delete it. Members must clear every direct balance before leaving, and the last admin must promote someone first. Groups can be deleted only when all balances are zero.

Receipt images, audio and drafts are processed in memory and are not stored by the application. Voice entry sends audio to Sarvam, then the transcript and group usernames to Groq. Provider policies apply to those requests. Receipt recognition can need manual corrections.

The app records payment claims and confirmations; it does not transfer money. INR is the only supported currency. Minimum-transfer search has exponential worst-case cost and is intended for small groups. Email verification and guest participants are not implemented. The [Render guide](SETUP.md#publish-on-render) covers publishing a reviewer demo with Neon PostgreSQL.
