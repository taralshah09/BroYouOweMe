# Submission

## Files to submit

| Requirement | File or link |
|---|---|
| GitHub repository | https://github.com/taralshah09/BroYouOweMe |
| Live app | `<render-app-url>` — replace with the actual Render URL before submitting |
| Demo login | `<render-app-url>/login` — credentials below |
| README | [README.md](README.md) |
| Setup instructions | [SETUP.md](SETUP.md) |
| API documentation | [API.md](API.md) |
| Database schema explanation | [SCHEMA.md](SCHEMA.md) |
| Postman collection | [BroYouOweMe.postman_collection.json](BroYouOweMe.postman_collection.json) |
| Postman local environment | [BroYouOweMe.local.postman_environment.json](BroYouOweMe.local.postman_environment.json) |
| Postman instructions | [POSTMAN.md](POSTMAN.md) |
| Demo video | [Watch on YouTube (unlisted)](https://youtu.be/lcuZM38lUzQ) |
| Demo walkthrough | [DEMO.md](DEMO.md) |
| Validation results | [VALIDATION.md](VALIDATION.md) |

## Description for the submission form

BroYouOweMe is a shared-expense app built with Django and PostgreSQL. Users create private groups, record expenses, split bills equally or by exact amounts, and track who owes whom. Payments change balances only after the receiver confirms them. The app also includes receipt review, voice entry, minimum-transfer suggestions, monthly insights, CSV export and an activity history.

The repository includes setup instructions, API documentation, a database schema explanation and a Postman collection. The automated Postman folder covers the three-person dinner example and checks balance changes, permissions, expense corrections and settlement confirmation.

Try the live app at `<render-app-url>` without signing up. Log in with **`reviewer_mohit`**, **`reviewer_rahul`** or **`reviewer_ankit`**; all use password **`BroYouOweMeDemo2026!`**. Open **Goa Trip (Demo)** to explore a pre-seeded INR 1,200 dinner split equally three ways. As Rahul, claim an INR 400 payment to Mohit; then sign in as Mohit and confirm it to see the balance change. The shared demo may reflect earlier reviewers' edits. Full instructions are in [DEMO.md](DEMO.md#try-the-hosted-demo).

Before submission, deploy using [SETUP.md](SETUP.md#publish-on-render), replace every `<render-app-url>` placeholder with Render's assigned HTTPS URL, verify all three logins, and add `<render-app-url>/health` to the external keep-alive cron (10-minute interval recommended).

## Review order

1. Open the live app and use the demo credentials above, or follow [SETUP.md](SETUP.md) to run locally.
2. Watch the demo for the main expense and payment flow.
3. Run **01 Automated submission flow** from the Postman collection.
4. Read [SCHEMA.md](SCHEMA.md) for money storage and ledger rules.
5. Run the Django tests against a disposable PostgreSQL database.

## Repository handoff

The repository contains the submission documents, Postman files, Render Blueprint and branding assets. Deploy the version containing these files, then replace the live URL placeholders before submitting. Repository rules in [CODEX.md](CODEX.md) require authorization for Git operations.

Use [the unlisted YouTube demo](https://youtu.be/lcuZM38lUzQ) for the submission's video link. Do not include `.env`, real API keys, database credentials or exported session cookies.
