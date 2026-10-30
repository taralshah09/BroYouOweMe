# API (through Phase 7)

All paths omit trailing slashes. Requests may be JSON objects or HTML form
submissions. GET defaults to JSON; send `Accept: text/html` for SSR pages.
`/`, `/signup`, and `/login` serve HTML on GET. Every route except signup,
login, health, and invite preview requires session authentication. Anonymous invite acceptance is also allowed to start the signup flow. Unauthenticated JSON requests
return 401; browser requests redirect to login. Unsupported methods return 405.
Bad inputs return 400, denied group access returns 403, missing rows return 404.
Validation JSON uses `errors`; access errors use `error`. Unmatched URLs (including removed `/users`) use Django's standard 404 response.

## Authentication and CSRF

1. GET `/signup` or `/login` to receive the CSRF cookie.
2. Send its value in `X-CSRFToken` on JSON POSTs (or the hidden form field).
3. Preserve the session cookie. Signup/login rotate the CSRF token, so use the
   current cookie for later requests. CSRF checks are never exempted.

Signup: `POST /signup` with
`{"username":"Mohit","email":"mohit@example.com","password":"your strong password"}`.
Returns 201 with `{"id":1,"username":"Mohit"}` and starts a session. HTML forms
use `password1` and `password2` for confirmation. Email and username are unique
without regard to case. Usernames are limited to 32 characters and cannot contain
`@`, keeping email login unambiguous. Email verification is not required.

Login: `POST /login` with `{"username":"Mohit","password":"your strong password"}`.
The `username` field also accepts an email, case-insensitively. Returns the same
user object with 200. `POST /logout` ends the session; GET is not allowed.
`/users` is removed; GET and POST return 404. There is no global user directory.

## Groups

| Method | Path | Input / output |
|---|---|---|
| GET | /groups | List caller's active groups |
| POST | /groups | `{"name":"Goa Trip"}`; 201 group object |
| GET | /groups/{id} | Group object or SSR dashboard |
| GET | /groups/{id}/members | List `user_id`, `username`, `role` |
| POST | /groups/{id}/members | `{"user_id":2}`; admin only, 201 member object |

Group objects contain `id`, `name`, `created_by`. The creator becomes the first
admin. Adding a duplicate member returns 400. Only existing active registered
users can be added. No removal, deletion, or role-changing routes exist yet.

## Expenses

`POST /expenses`:

```json
{"group_id":1,"paid_by":1,"amount":1200,"description":"Dinner"}
```

`expense_date` is optional (`YYYY-MM-DD`, defaults to today; backdating allowed).
All current members participate by default. Optional `participants` is a nonempty
list of unique active member IDs for an equal subset. Every share must be positive,
so the amount must cover at least one paisa per participant. The payer and creator must be
active members. Description is required, up to 200 characters. Optional fields include `category` (category ID or null), `tag` (up to 40 characters),
`split_mode` (`equal` or `unequal`), and `splits` (below). Unsupported fields,
including receipt items and AI source, return 400.

Returns 201 with `id`, `group_id`, `created_by`, `description`, `amount`,
`paid_by` (username), `paid_by_id`, and `expense_date`.
`GET /groups/{id}/expenses` lists those objects, newest creation first.
`GET /expenses/{id}` also includes `splits` with `user_id`, `username`, and `amount`.
Shares are stored in explicit split rows. Responses also contain `split_mode`,
`category` (ID or null), and `tag`. List filters: `category`, `date_from`, `date_to`
(inclusive YYYY-MM-DD), and `search` (description or tag).

Money inputs are rupees: integer, exact JSON decimal, or string with up to two
decimal places. No exponent, excess precision, nonfinite number, or negative/zero
expense is accepted. Storage and calculations use integer paise. Whole-rupee
outputs are JSON integers (matching the assignment); fractional outputs are
exact strings, e.g. `"33.33"`. No binary floats enter money calculations.
Remainder paise go to ascending user IDs. IDs must be positive bigint integers.

## Balances

`GET /groups/{id}/balances` returns nonzero pairwise group debts. The exact
Mohit/Rahul/Ankit Dinner 1200 scenario returns:

```json
{"Rahul":{"owes":{"Mohit":400}},"Ankit":{"owes":{"Mohit":400}}}
```

The payer's share never becomes a debt to themselves. Opposite debts net within
each pair. `GET /balances` combines the caller's pairs across active groups;
it does not expose pairs between other people. Both return `{}` when settled.
Settlements and display-only simplification are available below.

`GET /health` returns 200 `{"status":"ok"}` or 503
`{"status":"unavailable"}` based on a database query.

## Editing and unequal splits

For exact allocations, supply `splits` as rupee amounts:

```json
{"group_id":1,"paid_by":1,"amount":"1200.01","description":"Dinner",
 "splits":[{"user_id":1,"amount":"400.00"},{"user_id":2,"amount":"800.01"}]}
```

Omitting `split_mode` infers unequal when `splits` is supplied, otherwise equal.
Each split requires exactly `user_id` and `amount`. IDs must be unique active
members; amounts must be positive and sum exactly to the total. If supplied,
`participants` must match the split users. Equal mode accepts `participants`
and rejects explicit splits. The payer need not be a participant.

`PATCH /expenses/{id}` accepts any subset of the create fields except `group_id`.
Only the creator, while still a group member, may edit or delete. With no split
fields, equal edits preserve the original participants and recompute shares;
unequal edits preserve the exact amounts (a changed total must still match).
Supplying split fields replaces the allocation. `category: null` clears the category.
Edits atomically reverse old debts, apply new ones, and append before/after audit
snapshots. `DELETE /expenses/{id}` soft-deletes and reverses debts; returns
`{"deleted":true}`. Deleted rows are excluded from reads. Both operations can
reverse a debt's direction after previously confirmed payments.

Browser forms use `POST /expenses/{id}` to edit and
`POST /expenses/{id}/delete` to delete, with the same permissions and CSRF checks.

## Categories

`GET /groups/{id}/categories` returns default and group categories as
`{"id":1,"name":"Food","group_id":null}` objects. Built-in defaults are Food,
Travel, Stay, Shopping, Entertainment, Utilities, and Other.

Any member can `POST /groups/{id}/categories` with `{"name":"Booze"}` (201),
`PATCH /groups/{id}/categories/{category_id}` with a new name (200), or
`DELETE` an unused custom category (200, `{"deleted":true}`). Default names
and group names are case-insensitively unique within their applicable scope.
Defaults cannot be changed. Cross-group assignments are rejected. Used categories
can be renamed but never deleted, including use by soft-deleted expenses.
Browser forms use POST on the category URL to rename or `action=delete` to delete.

## Settlements

`POST /settlements` with `{"group_id":1,"receiver":1,"amount":"100.01","note":"Cash"}`
creates a pending claim (201). The authenticated user is always the payer.
The receiver must be another active member with a real pairwise debt owed by
the payer. A claim plus other pending claims for this direction cannot exceed
the current debt. Partial payments, from one paisa, are allowed. Note is optional,
up to 200 characters. Pending claims do not change balances.

`GET /groups/{id}/settlements` returns newest-first claims. Objects contain `id`,
`group_id`, `payer`, `receiver` (IDs), `payer_username`, `receiver_username`,
`amount` (rupees), `status`, `note`, `created_at`, and `resolved_at` (null if pending).

POST an empty object to `/settlements/{id}/confirm` or `/reject` as the receiver,
or `/cancel` as the payer. Only pending claims can be resolved. Confirmation
rechecks the amount plus other pending claims against the current debt while
holding the group lock, then reduces that debt atomically. Rejection/cancellation
releases the reservation without changing balances. A resolved claim cannot be
replayed; stale or excessive claims return 400. Edits can invalidate pending
claims; cancel or reject them to release reservations.

## Activity and integrity

`GET /groups/{id}/activity?page=1` returns `page`, `pages`, and `results`, 25 per page,
newest first. Each event includes `id`, `actor` (username), `action`, `entity_type`,
`entity_id`, `before`, `after`, and `created_at`. Expense and settlement snapshot
amounts are explicitly named `amount_paise`/`share_paise` and use integer paise;
regular endpoint amounts continue to use rupees. Events are appended in the same
transaction as the operation and have no mutation endpoints. Category operations
are also logged. The browser feed formats snapshots as rupees and usernames.

The migration materializes Phase 1 participants using membership join times,
retains existing balances, and seeds creation events at original expense creation
times. `python manage.py check_balances` verifies stored share totals and recomputes
all active expense debts minus confirmed settlements under group locks.


## Suggested settlements (Phase 3)

`GET /groups/{id}/simplified` requires active membership. JSON returns
`{"display_only":true,"transfers":[{"payer":2,"payer_username":"Rahul","receiver":1,"receiver_username":"Mohit","amount":400}]}`.
The exact algorithm minimizes transfer count across net group balances. It does not
write balances, reserve pending claims, or create settlements. Suggestions may
connect people without a direct debt; actual claims still require pairwise debt.
Accept: text/html renders the suggestions screen.

## Invites (Phase 4)

- `GET /groups/{id}/invites`: admin-only list, including revoked/expired history.
- `POST /groups/{id}/invites`: admin-only creation, empty body; 201 with `id`,
  absolute `url`, relative `qr_url`, `active`, `expires_at`, and `revoked_at`.
- `POST` or `DELETE /groups/{id}/invites/{invite_id}`: admin-only revocation.
- `GET /groups/{id}/invites/{invite_id}/qr`: admin-only SVG QR generated locally
  in memory. Inactive links return 404.
- `GET /invite/{token}`: public preview with only `group_name` and `member_count`.
- `POST /invite/{token}/join`: authenticated users join; JSON returns `group_id`.
  Anonymous HTML users go to signup; JSON returns 401 with `signup_required: true`.
  The session remembers the explicitly accepted invite and auto-joins after signup
  or login (JSON includes `group_id`). Invalid forms retain the pending invitation.

Links are random, multi-use, and expire after seven days. Revocation and group
soft deletion make them unusable. Joining preserves historical splits. Repeat joins
duplicate neither membership nor activity; rejoining restores member role. Joining
and revocation serialize on the group lock. Expiry during signup still allows the
account to be created, without joining. Preview GET never changes pending invites.
All mutations require CSRF. Generate links from the canonical reachable host.

Member additions also accept `{"username":"exact_username"}` case-insensitively.
Known `user_id` values remain supported by the API. Neither UI enumerates platform
accounts; group member lists require active membership.


## Phase 5 receipt entry

`GET /groups/{id}/receipts` opens the upload and correction screen. Creator edits
use `?expense={expense_id}`. `POST /groups/{id}/receipts/parse` accepts multipart
`image` (JPEG/PNG/WebP, up to 8 MiB / 20 megapixels), requires membership and CSRF,
and returns `{items, amount, warnings, text}` without any database writes. OCR
failure returns a generic validation error. Drafts and images are never persisted.

Approval uses JSON `POST /expenses` with the normal fields plus `source: "ocr"`,
`split_mode: "equal"` or `"itemised"`, and `items`. Each item has `kind` (`item`,
`tax`, `service`, `tip`, `discount`), `name`, exact rupee `amount`, and optional
`payees` (unique selected participant IDs; item lines only). Discounts must be
negative; other lines positive. One to 100 lines are accepted. At least one item
is required, and all lines must sum to the expense amount. The caller must be the
payer. Participants default to all active group members. Itemised shares divide
items equally among their payees, defaulting to all participants. Combined charges
and discounts are divided equally among item recipients. Remainders go to ascending
user IDs; every final share must be positive. Explicit `splits` are rejected for OCR.

`GET /expenses/{id}` includes `source` and `items`. `PATCH /expenses/{id}` can
correct receipt items, amount, participants and mode; omitted items and source
are preserved, and changing an OCR expense to manual is rejected. Receipt edits,
items, split replacement, balances and audit snapshots commit atomically. Existing
creator-only edit/delete and membership checks apply. Soft deletion retains items.


## Phase 6 voice entry

- `GET /groups/{id}/voice`: member-only recording, transcript and editable approval screen.
- `POST /groups/{id}/voice/parse`: multipart `audio` (mono 16 kHz, 16-bit WAV,
  max 2 MiB / 30 seconds) or JSON `{"transcript":"I paid 600 for dinner"}`
  (1?4000 characters). Returns `{transcript, draft}` where draft contains `amount`
  (exact rupee string or null), `description`, `paid_by` (member ID or null),
  `participants` (member IDs), `warnings`, `source: "voice"`, `split_mode: "equal"`.
  Ambiguous members are unselected. No expense or balance is written. Errors are
  400 for invalid inputs and 503 for unavailable/unconfigured providers. If Groq
  fails after transcription, the 503 response includes `transcript` for correction.
- `POST /groups/{id}/voice/approve`: HTML form with normal `ExpenseForm` fields
  and mandatory `approved=yes`; validates the reviewed fields and saves through
  the expense service with source=voice. Success redirects to the expense detail.
  Validation errors preserve entered form values. All endpoints require active
  membership and POSTs require CSRF. Voice pages/responses are not cacheable.

Clients may also submit reviewed JSON to normal `POST /expenses` with
`source: "voice"`. Equal/subset and exact unequal shares use the existing API
rules; voice does not accept receipt items. Creator-only edit/delete, audit
snapshots and atomic ledger updates apply to voice expenses too. Never submit
provider output automatically; show it for explicit review first.
## Phase 7: Insights, export and reminders

All three endpoints require a session and active group membership. Reads never
change the ledger. Responses use `Cache-Control: no-store`. Use `Accept: text/html`
for the insights and reminders pages; otherwise they return JSON.

| Method | Path | Response |
|---|---|---|
| GET | `/groups/{id}/insights?month=2026-10` | Month summary, category totals, twelve monthly totals |
| GET | `/groups/{id}/expenses/export.csv?month=2026-10` | CSV attachment, optionally filtered to one month |
| GET | `/groups/{id}/nudges` | `{"nudges": [{"user_id": 2, "username": "bob", "amount": "3.00", "pending_amount": "2.00", "text": "..."}]}` |

`month` must be a valid `YYYY-MM` between `0002-01` and `9998-12`; invalid/empty
values return 400. Insights defaults to the current UTC month. CSV defaults to all
dates. Other dates follow the existing expense API.

Insights response fields: `group_id`, `month`, `currency: "INR"`,
`summary: {total, expense_count, your_paid, your_share}`, `categories: [{id, name,
amount}]`, and `months: [{month, amount}]` in ascending order. Money is always a
two-decimal string. Category totals cover the selected month; monthly totals cover
the twelve months ending with it. No category is represented by `id: null` and
`name: "Uncategorised"`. Totals include only active expenses in that group, using
`expense_date`. Settlements never reduce spending. Personal totals are for the caller.

CSV columns: `expense_id, expense_date, description, category, tag, source, paid_by,
amount_inr, your_share_inr, splits_inr`. One row per active expense; named splits
use `username: amount; username: amount` in user-ID order. User text is quoted by
the CSV writer and protected against spreadsheet formula execution with a leading
apostrophe when needed. The download contains no email addresses or account directory.

Nudges cover only direct debts owed to the caller. Amounts reserved by pending
claims are excluded and reported separately; fully reserved debts are omitted.
Amounts come from current pairwise balances, not simplified suggestions. This
endpoint generates text only and sends no messages or notifications.
