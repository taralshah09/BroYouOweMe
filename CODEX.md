# CODEX.md: Hard Rules for This Repo

These rules apply to every contributor and every AI agent working here. If a rule gets in the way, stop and ask. Do not work around it.

## 1. Process
1. **Ask, never assume.** If a requirement, behaviour or edge case is unclear, ask the owner before implementing it.
2. **No implementation before approval.** Do not write application code until the owner says to start. Planning and docs are fine.
3. **The docs are the source of truth.** `docs/PLAN.md` (features, phases, locked decisions) and `docs/SCHEMA.md` (tables, API) define what is built. Do not deviate from them. If a change is needed, propose it, get approval, then update the docs in the same change as the code.
4. **Phases in order.** Build phase by phase as listed in `docs/PLAN.md`. Do not start a phase early or add features that are not in the plan.
5. **Report honestly.** If tests fail or something was skipped, say so with the output.

## 2. Git and GitHub
1. **No commits, pushes, branches, tags or pull requests until the owner has explicitly approved that specific action.** Approval for one action does not carry over to the next.
2. Never force-push, rewrite history or skip hooks.
3. Never commit secrets, `.env` files, API keys, database URLs or user data.
4. Show the owner what will be committed (files and message) before asking for approval.

## 3. Repo structure (do not change without approval)
```
BroYouOweMe/
├── CODEX.md              this file
├── README.md             setup, architecture, schema explanation, assumptions, decisions, future work
├── Assignment.pdf        the original assignment (read-only)
├── docs/                 PLAN.md, SCHEMA.md, API docs, other documentation
├── manage.py
├── config/               Django settings, root urls, wsgi/asgi
├── apps/                 one Django app per domain:
│   ├── accounts/         users, auth
│   ├── groups/           groups, members, roles, invites
│   ├── expenses/         expenses, splits, items, categories
│   ├── settlements/      settlements, balances, simplification
│   ├── activity/         activity log and feed
│   ├── insights/         analytics, CSV export, nudges
│   └── ai/               receipt OCR and voice parsing (Tesseract, Sarvam, Groq clients)
├── templates/            Django templates (SSR)
├── static/               css/ and js/ only; plain HTML, CSS and JS, no frontend framework
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example          variable names only, never real values
```
- New files go in the folder that matches their domain. Do not create new top-level folders or files.
- Business logic lives in each app's `services` module, not in views or templates. Views stay thin.
- Tests live in each app's `tests/` folder.
- Documentation lives in `docs/`, except `README.md` and this file.
- The structure above is a proposal until the owner approves it. After approval, changes need approval too.

## 4. Tech constraints
- Python and Django, server-side rendered. No React or other frontend framework.
- PostgreSQL on Neon. Deployed on Render (Docker, free tier).
- Receipt OCR: Tesseract. Voice transcription: Sarvam only. LLM parsing and tool calling: OpenAI SDK pointed at Groq.
- Uploaded images and audio are processed in memory and never stored.

## 5. Money and data integrity
1. Money is integer paise. Never use floats for money.
2. Splits always sum exactly to the expense total. Remainder paise follow the rule in `docs/SCHEMA.md`.
3. Every balance-changing operation (expense create/edit/delete, settlement confirm) goes through the service layer, in one database transaction, with the group row locked.
4. Never write to the `balances` table from anywhere else.
5. Expenses are soft-deleted. The activity log is append-only.
6. Every view checks that the user is an active member of the group (and an admin where required). Integer IDs are guessable.
7. AI-assisted entry (OCR and voice) never saves anything on its own. The user must review and approve first.

## 6. Quality
- Match the surrounding code's style, naming and comment density.
- Add unit tests for expense creation, balance calculation, validation and any new business rule. The balance integrity check must pass.
- Secrets come from environment variables only.
- Keep changes small and focused. No unrelated refactors.
