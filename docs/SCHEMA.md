# BroYouOweMe: Database Schema and API Design

Status: domain schema not yet implemented; Phase 0 scaffold only. Built from the decisions in `PLAN.md`.
Anything marked **DECISION NEEDED** is not settled and must not be implemented until answered.

## 1. Conventions

- PostgreSQL on Neon. Django models; table names below are logical names.
- Primary keys: auto-increment `bigint` (decided). Every view must verify group membership, because IDs are guessable.
- Money: integer paise in `*_paise` columns (`bigint`). Never floats.
- Timestamps: `timestamptz`, UTC.
- Soft delete: a nullable `deleted_at` column. Default queries exclude rows where it is set.
- Rounding rule: when a total does not divide evenly, divide with floor and give the leftover paise one each to participants in ascending `user_id` order. Shares always sum exactly to the total.

## 2. Entity overview

```
users ──< group_members >── groups ──< invites
  │                           │
  │                           ├──< expenses ──< expense_splits >── users
  │                           │        └──< expense_items ──< expense_item_payees >── users
  │                           ├──< settlements
  │                           ├──< balances (one row per user pair per group)
  │                           └──< activity_log
categories (group-specific, or global defaults) ──< expenses
```

## 3. Tables

### users
Custom Django user model (extends `AbstractUser` or `AbstractBaseUser`; decide at implementation).

| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| username | varchar(32) | The user's identity everywhere (UI, API, balances JSON). Unique, case-insensitive (unique index on `lower(username)`). |
| email | varchar(254) | Unique, case-insensitive. An account can be created from an email. |
| password | varchar | Django hashed password. |
| created_at | timestamptz | |

There is no separate display name (decided): the username is the source of truth. Login works with either email or username (like Twitter). Email verification is not required for now.

### groups
| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| name | varchar(100) | |
| created_by | FK users | |
| created_at | timestamptz | |
| deleted_at | timestamptz null | Soft delete; allowed only when all balances are zero. |

### group_members
| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| group_id | FK groups | |
| user_id | FK users | |
| role | varchar(10) | `admin` or `member`. CHECK constraint. |
| joined_at | timestamptz | |
| left_at | timestamptz null | Null means currently a member. |

- UNIQUE (group_id, user_id). Rejoining via an invite clears `left_at` on the existing row.
- Index (user_id) WHERE left_at IS NULL, for "my groups".
- Invariant, enforced in the service layer inside a transaction that locks the group row: a group always has at least one active admin. An admin cannot leave or be demoted if they are the last admin, and must promote someone first (no auto-promotion).
- Invariant: a member can leave only if all their balances in the group are zero.
- Admins can remove other members, including other admins (decided). Removal needs the member's balances in the group to be zero, like leaving. The last-admin invariant still holds.

### categories
Categories can be group-specific (e.g. "Booze" on the Goa Trip group exists only there). Default categories are shared by all groups.

| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| group_id | FK groups null | Null means a built-in default visible to every group. Set means the category belongs to that group only. |
| name | varchar(40) | |
| created_by | FK users null | Null for defaults. |
| created_at | timestamptz | |

- Built-in defaults, seeded by a data migration with `group_id` null: Food, Travel, Stay, Shopping, Entertainment, Utilities, Other (confirmed).
- UNIQUE (group_id, lower(name)) for group categories, and a separate unique index on `lower(name)` WHERE group_id IS NULL for defaults. A group cannot create a category that duplicates a default's name.
- An expense may only use a default category or a category of its own group. Enforced in the service layer.
- Any group member can create, rename and delete group categories (decided).
- A category cannot be deleted if any expense is linked to it, including soft-deleted expenses. `expenses.category_id` uses a protective foreign key (`ON DELETE RESTRICT`), and the service layer returns a clear error. Unused categories are deleted for real, so there is no `deleted_at` on this table.
- Built-in defaults cannot be edited or deleted.

### expenses
| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| group_id | FK groups | |
| created_by | FK users | The only user allowed to edit or delete it. |
| paid_by | FK users | Must be an active group member. |
| amount_paise | bigint | CHECK > 0. |
| description | varchar(200) | |
| category_id | FK categories null | |
| tag | varchar(40) null | Optional free-text tag. |
| expense_date | date | Defaults to today; can be backdated. Analytics use this. |
| split_mode | varchar(10) | `equal`, `unequal`, or `itemised`. |
| source | varchar(10) | `manual`, `ocr`, or `voice`. |
| created_at, updated_at | timestamptz | |
| deleted_at | timestamptz null | Soft delete. |

Indexes: (group_id, expense_date DESC) WHERE deleted_at IS NULL; (group_id, category_id).

### expense_splits
Who owes what share of an expense. Covers equal, unequal, subset and itemised splits uniformly.

| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| expense_id | FK expenses | |
| user_id | FK users | Must have been an active member when the expense was saved. |
| share_paise | bigint | CHECK > 0. |

- UNIQUE (expense_id, user_id).
- Invariant: `SUM(share_paise) = expenses.amount_paise`. Postgres cannot check this across rows without a trigger, so it is enforced in the service layer and verified by tests and the integrity check.
- The payer may have a split row (their own share). It never creates a debt, because the payer does not owe themselves.

### expense_items
Line items from a receipt. Present only for `source = ocr` or `split_mode = itemised`.

| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| expense_id | FK expenses | |
| kind | varchar(10) | `item`, `tax`, `service`, `tip`, `discount`. CHECK. |
| name | varchar(120) | |
| price_paise | bigint | Positive, except `discount`, which is negative. |
| position | smallint | Order on the receipt. |

Invariant: `SUM(price_paise)` over the expense's items equals `expenses.amount_paise`.

### expense_item_payees
| Column | Type | Notes |
|---|---|---|
| item_id | FK expense_items | |
| user_id | FK users | |

PRIMARY KEY (item_id, user_id). Only for `kind = item`. An `item` row with no payees means "split among all participants" (decided).

Itemised split computation (done at save time, written to `expense_splits`):
1. Each `item` price is divided equally among its payees (all participants if it has none), using the rounding rule.
2. `tax`, `service`, `tip` and `discount` totals are divided equally among every user who has at least one item share (decided), using the rounding rule.
3. Each user's resulting amounts are summed into one `expense_splits` row.

### settlements
| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| group_id | FK groups | |
| payer_id | FK users | The person who paid. |
| receiver_id | FK users | The person who received the money. |
| amount_paise | bigint | CHECK > 0. |
| status | varchar(10) | `pending`, `confirmed`, `rejected`, `cancelled`. CHECK. |
| note | varchar(200) null | |
| created_at | timestamptz | When the payer claimed it. |
| resolved_at | timestamptz null | When confirmed, rejected or cancelled. |

- CHECK (payer_id <> receiver_id).
- Flow: the payer creates a `pending` settlement. The receiver confirms or rejects it. The payer can cancel while it is pending. Balances change only on confirmation.
- Amount rule (decided): partial allowed, no overpay. At creation, `amount + SUM(other pending settlements payer→receiver)` must not exceed what the payer currently owes the receiver in that group. The check is repeated at confirmation under the group lock, because balances can change in between.
- Index (group_id, status).
- Settlements are always between two users who have a real pairwise debt (decided). Debt simplification is display only and is never executed as a settlement.

### balances
Maintained pairwise net balance per group (decided: maintained table).

| Column | Type | Notes |
|---|---|---|
| group_id | FK groups | |
| user_a_id | FK users | The user with the smaller id. |
| user_b_id | FK users | The user with the larger id. |
| net_paise | bigint | Positive: b owes a. Negative: a owes b. Zero: settled. |

- PRIMARY KEY (group_id, user_a_id, user_b_id); CHECK (user_a_id < user_b_id).
- One row per unordered pair, so opposite debts net automatically.
- Updates are one atomic statement: `INSERT ... ON CONFLICT (group_id, user_a_id, user_b_id) DO UPDATE SET net_paise = balances.net_paise + EXCLUDED.net_paise`.
- Reading: expand each non-zero row into "debtor owes creditor amount" for the API.
- Group totals and the overall `GET /balances` view are sums over these rows.

### invites
| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| group_id | FK groups | |
| token | varchar(64) | Cryptographically random, URL-safe, unique. The only unguessable identifier in the system. |
| created_by | FK users | Must be an admin. |
| created_at | timestamptz | |
| expires_at | timestamptz | `created_at + 7 days` (decided). |
| revoked_at | timestamptz null | Admins can revoke. |

Multi-use: a link works until it expires or is revoked. Each join is recorded in `activity_log`.

### activity_log
Append-only audit trail and the source of the activity feed.

| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| group_id | FK groups | |
| actor_id | FK users | |
| action | varchar(40) | e.g. `expense.created`, `expense.updated`, `expense.deleted`, `settlement.claimed`, `settlement.confirmed`, `member.joined`, `member.left`, `role.changed`, `invite.created`, `invite.revoked`, `group.deleted`. |
| entity_type | varchar(30) | |
| entity_id | bigint | |
| before | jsonb null | Previous values (edits, deletes). |
| after | jsonb null | New values. |
| created_at | timestamptz | |

Index (group_id, created_at DESC). Rows are never updated or deleted.

## 4. Transactional balance maintenance

All balance-changing operations go through one service layer and run in a single database transaction. Each starts by locking the group row (`SELECT ... FOR UPDATE`), which serialises changes per group, avoids deadlocks and keeps balances consistent.

| Operation | Balance effect |
|---|---|
| Create expense | For every split row where `user_id <> paid_by`, that user owes the payer `share_paise`. Apply as one delta per pair. |
| Edit expense | Reverse the deltas of the old splits, apply the new ones. Log before/after in `activity_log`. |
| Delete expense | Soft-delete, reverse the deltas. |
| Confirm settlement | Payer owes the receiver `amount_paise` less. |
| Member leave / group delete | Pre-check that balances are zero. No balance change. |

Edge cases to be aware of:
- Editing or deleting an expense after related settlements can flip a pair's direction. This is allowed, and the balance simply reflects the new truth.
- Because only the creator can edit or delete an expense, a former member's expenses become uneditable by anyone. This follows from your rules.

Integrity check: a function recomputes every pair from the ledger (non-deleted expenses plus confirmed settlements) and compares it with `balances`. It runs in the test suite and is available as a management command. Any mismatch is a bug.

## 5. API design

All endpoints require login except signup, login, the health check and invite preview. Responses are JSON. The same views feed the SSR pages where relevant. Amounts in requests and responses are in rupees (e.g. `1200` or `1200.50`) as in the assignment, and converted to paise internally.

### Auth and users
| Method | Path | Notes |
|---|---|---|
| POST | /signup | Email-based account creation (with a chosen username). Also serves as the assignment's "create user". |
| POST | /login, /logout | Session auth. Login with email or username plus password. |
| POST | /users | Assignment endpoint; same behaviour as signup. |
| GET | /users | All users, as the assignment requires. |

### Groups and members
| Method | Path | Notes |
|---|---|---|
| POST | /groups | Creator becomes the first admin. |
| GET | /groups | The caller's groups. |
| DELETE | /groups/{id} | Admin only, only if all balances are zero. |
| POST | /groups/{id}/members | Admin adds an existing user (`user_id`), as in the assignment. |
| GET | /groups/{id}/members | |
| PATCH | /groups/{id}/members/{user_id} | Admin changes a role. |
| DELETE | /groups/{id}/members/{user_id} | A member leaves (self), or an admin removes someone. |

### Categories
| Method | Path | Notes |
|---|---|---|
| GET | /groups/{id}/categories | Built-in defaults plus this group's own. |
| POST | /groups/{id}/categories | Any member creates a group-only category. |
| PATCH / DELETE | /groups/{id}/categories/{category_id} | Any member renames or deletes a group category. Delete is refused if any expense uses it. |

### Invites
| Method | Path | Notes |
|---|---|---|
| POST | /groups/{id}/invites | Admin only. Returns link and QR. |
| DELETE | /groups/{id}/invites/{invite_id} | Admin revokes. |
| GET | /invite/{token} | Public preview (group name, member count). |
| POST | /invite/{token}/join | Logged-in user joins. Anonymous users go to signup first, then back here. |

### Expenses
| Method | Path | Notes |
|---|---|---|
| POST | /expenses | Body per assignment (`group_id`, `paid_by`, `amount`, `description`), extended with optional `participants`, `splits`, `items`, `category`, `tag`, `expense_date`. |
| GET | /groups/{id}/expenses | Filters: category, date range, search text. |
| GET | /expenses/{id} | Includes splits and items. |
| PATCH / DELETE | /expenses/{id} | Creator only. |

### Balances, simplification and settlements
| Method | Path | Notes |
|---|---|---|
| GET | /groups/{id}/balances | Assignment format, keyed by username: `{"rahul": {"owes": {"mohit": 400}}}`. |
| GET | /balances | The caller's net position across all groups. |
| GET | /groups/{id}/simplified | Suggested minimum set of transfers. Display only. |
| POST | /settlements | Payer claims a payment. |
| GET | /groups/{id}/settlements | |
| POST | /settlements/{id}/confirm, /reject, /cancel | Receiver confirms or rejects, payer cancels. |

### AI-assisted entry (nothing is saved until the user approves)
| Method | Path | Notes |
|---|---|---|
| POST | /groups/{id}/receipts/parse | Image upload, Tesseract, returns a draft (items, charges, total). Processed in memory and not stored. |
| POST | /groups/{id}/voice/parse | Audio upload, Sarvam transcription, Groq parsing, returns a draft expense. Processed in memory and not stored. |

Drafts are stateless: they are returned to the browser and shown on the review screen. "Approve" submits a normal `POST /expenses` with `source = ocr` or `voice`. No draft table is needed.

### Insights, activity and operations
| Method | Path | Notes |
|---|---|---|
| GET | /groups/{id}/activity | Paginated feed. |
| GET | /groups/{id}/insights | Category and monthly totals. |
| GET | /groups/{id}/expenses/export.csv | CSV export. |
| GET | /groups/{id}/nudges | Pre-filled reminder text for people who owe. |
| GET | /health | For the external pinger; runs `SELECT 1`. |

## 6. Decisions

### Settled
- Debt simplification is display only (settlements stay between real pairwise debts).
- Admins can remove other members.
- API money format is rupees with up to two decimals, converted to paise internally.
- Default categories: Food, Travel, Stay, Shopping, Entertainment, Utilities, Other.
- Categories can also be created per group and are visible only inside that group.
- No display names. Username is the identity everywhere. Users also have a unique email, and an account can be created from an email.

- Login with either email or username. No email verification for now.
- Any member can manage group categories. A category can be renamed even when in use, but cannot be deleted once any expense uses it.
- The free-text `tag` column on expenses stays.
- Admins can remove other members, including admins. Removal requires zero balances.

### Still open
- None.
