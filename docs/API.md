# Phase 1 API

All paths omit trailing slashes. Requests may be JSON objects or HTML form
submissions. GET defaults to JSON; send `Accept: text/html` for SSR pages.
`/`, `/signup`, and `/login` serve HTML on GET. Every route except signup,
login, and health requires session authentication. Unauthenticated JSON requests
return 401; browser requests redirect to login. Unsupported methods return 405.
Bad inputs return 400, denied group access returns 403, missing rows return 404.
Validation JSON uses `errors`; access and routing errors use `error`.

## Authentication and CSRF

1. GET `/signup` or `/login` to receive the CSRF cookie.
2. Send its value in `X-CSRFToken` on JSON POSTs (or the hidden form field).
3. Preserve the session cookie. Signup/login rotate the CSRF token, so use the
   current cookie for later requests. CSRF checks are never exempted.

Signup: `POST /signup` or `POST /users` with
`{"username":"Mohit","email":"mohit@example.com","password":"your strong password"}`.
Returns 201 with `{"id":1,"username":"Mohit"}` and starts a session. HTML forms
use `password1` and `password2` for confirmation. Email and username are unique
without regard to case. Usernames are limited to 32 characters and cannot contain
`@`, keeping email login unambiguous. Email verification is not required.

Login: `POST /login` with `{"username":"Mohit","password":"your strong password"}`.
The `username` field also accepts an email, case-insensitively. Returns the same
user object with 200. `POST /logout` ends the session; GET is not allowed.
`GET /users` returns a list of active users with IDs and usernames only.

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
All current members participate. Every member's share must be positive, so the
amount must cover at least one paisa per member. The payer and creator must be
active members. Description is required, up to 200 characters. Unsupported
fields, including custom participants, splits, items, and AI source, return 400.

Returns 201 with `id`, `group_id`, `created_by`, `description`, `amount`,
`paid_by` (username), `paid_by_id`, and `expense_date`.
`GET /groups/{id}/expenses` lists those objects, newest creation first.
`GET /expenses/{id}` also includes `splits` with `user_id`, `username`, and `amount`.
These shares are calculated from membership at creation time in Phase 1.

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
No settlement or simplification routes exist in Phase 1.

`GET /health` returns 200 `{"status":"ok"}` or 503
`{"status":"unavailable"}` based on a database query.
