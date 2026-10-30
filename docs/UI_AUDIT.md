# Page structure and UI audit

Date: 2026-10-30. Baseline: Phase 7 implementation, before the owner's reference-led redesign.

## Coverage and evidence

- Reviewed all 23 template files: base shell, 19 full-page templates and three
  shared row partials. Those templates provide 21 page states because login/signup
  share a template and group/overall balances share another.
- Reviewed all four browser scripts, the shared CSS, routes, forms and relevant
  view/service permissions. No frontend framework is used.
- An integration audit renders all 21 states against disposable PostgreSQL,
  including populated groups, a custom category, pending settlement, invite,
  reminders, and a validation error. Every state has one `main`, one `h1`, unique
  IDs, valid explicit label targets and resolvable local links/form actions.
  This checks route existence, not whether every possible user can follow a link.
- Native Brave desktop review covered expense detail, group dashboard and spending
  insights. On the owner's follow-up request, the mobile review resumed and covered
  all 21 page states at verified 320px or 390px CSS widths (coverage below).
  Dedicated browser automation still reports `The browser access host is unavailable`;
  native browser device tools provided the responsive previews instead.
- The first review stopped when the owner pressed Escape. Browser interaction
  resumed only after the owner explicitly requested the remaining mobile checks.
- All pages have source and server-render checks. This is not a claim that every
  page, viewport, assistive technology or interactive state passed visual QA.
  Actual phone keyboard/OS behaviour, native clipboard/share, microphone permissions,
  real receipt uploads and full mobile transaction flows still need real-device trials.
- Tests use disposable PostgreSQL. Live app checks are read-only; no user ledger
  data was created for this audit. No messages were sent.

## Page inventory

### Completed mobile visual pass — 2026-10-30 follow-up

Used Brave's native responsive device toolbar, with the width fields verified at
320 or 390 CSS pixels and preview display scale set to 75%. Scrolled through long
pages to inspect lower forms/actions as well as headers. This is responsive browser
layout QA, not a physical iOS/Android device test. Each state below was inspected at
the listed width; this does not mean every state was tested at both widths.

| Page state | Width checked | Visual result |
|---|---|---|
| Home | 320 | Hero, CTA and stacked feature cards fit. |
| Login | 320 | Labels, fields, action and account link fit. No credentials entered. |
| Signup | 320 | Heading wraps; password help, confirmation and action fit. No signup submitted. |
| Group list | 320 | Group card and create form stack within viewport. |
| Group dashboard | 390, 320 | Links wrap, debt rows fit; long vertical route to expense form confirms F3. |
| Members | 390 | Username and role columns fit. |
| Invite management | 320 | Long URL wraps, QR scales within card, expiry and revoke action fit. |
| Invite preview | 320 | Group name, member count and join action fit; no join submitted. |
| Standalone expense history | 320, 390 | Amount-column defect found and fixed; long description wraps beside intact INR amount. |
| Expense detail/edit | 320 | Long description heading, share rows, edit controls and delete disclosure fit. No edits/deletion submitted. |
| Categories | 320 | Default-category cards and new-category form fit. Existing group had no custom-category edit state to inspect visually. |
| Receipt review | 390 | Upload/correction fields, participant checkboxes, dynamically added unsaved line, payee select, remove/add/approval actions fit. No upload/save performed. |
| Voice review | 390, 320 | Recording/transcript controls, review fields and approval fit. At 320 the long approval button wraps within the card. No recording/provider call/save performed. |
| My balances | 320 | Debt labels wrap beside intact amounts. |
| Group balances | 320 | Debt labels wrap beside intact amounts after shared row fix. |
| Settle up | 320 | Existing confirmed-payment card and receiver/amount/note/claim form fit. No claim/status action submitted. |
| Suggested settlements | 390, 320 | Names wrap; currency and amount stay together after shared row fix. |
| Activity | 320 | Cards, expanded before/after content and page count fit. Current data has one page, so next/previous controls were not visually exercised. |
| Spending insights | 390 | Month filter, stacked summary cards, category/month rows and both export links fit. No download triggered. |
| Payment reminders | 390 | Long reminder text, readonly fields and copy/share buttons fit. No reminder was sent or shared. |
| Validation error | 320 | Invalid-month error text and recovery button fit; generic copy issue F2 remains. |

The live authenticated session was preserved. Login/signup were inspected as
rendered forms within that session; logged-out header and invite signup continuation
were not replayed. All ledger reads were read-only. Adding a receipt line changed
only the browser draft, which was discarded when navigating away.

**Resolved defect:** at 320px, the flex layout let a long expense description squeeze
`INR 600` into fragments (`IN`, `R`, `60`, `0`). The same layout let suggested-settlement
currency and amount split across lines. `static/css/main.css` now allows the first
row column to shrink (`min-width: 0`) and keeps the trailing value from shrinking
or wrapping. Rebuilt the Docker app, reloaded the actual pages, and visually
verified expense history at 320/390 and suggested settlements at 320; group and
overall balances were also inspected with the final rule. No other blocking
layout defects were observed in the states above. F3/F4/F5/F6/F10 remain design
improvements for the reference-led redesign.

Physical-device keyboard behaviour, microphone permission/recording, real OCR
uploads, clipboard/share-sheet delivery, alternate role/empty/error variants and
end-to-end saves remain separate functional/device acceptance work.

All private group pages require active membership; invite management requires
admin membership. Expense editing/deletion is restricted to the creator.

| Page / route | Current structure and elements | Redesign considerations |
|---|---|---|
| Home `/` | Hero, primary signup/groups CTA, three feature cards | Copy describes equal splitting only; update to reflect receipt, voice and exact shares. |
| Signup `/signup` | Narrow auth card, username/email/password fields, error/help text, login link | Separate field layout and password hints; keep invite continuation visible. |
| Login `/login` | Shared auth card, username-or-email/password, signup link | Distinct page title; preserve destination after login. Password reset is outside the current plan. |
| Groups `/groups` | Group link cards and create-group form in two columns | Cards contain only names; define metadata, ordering, empty state and long-name wrapping. |
| Group `/groups/{id}` | Group title, six inline section links, balances, expense history, members, add-member form for admins, expense form | Main information hub is crowded; add hierarchy and a persistent group navigation pattern. On mobile the expense form follows the entire history/member column. |
| Members `/groups/{id}/members` | Username/role rows | Make membership navigation discoverable; lifecycle controls are absent (see F1). |
| Invites `/groups/{id}/invites` | Create action, URL, expiry/status, QR image, open-QR/revoke controls | Add copy feedback, friendly dates and clearer separation of active/expired/revoked links. Preserve admin scope. |
| Invite preview `/invite/{token}` | Group name/count, join/signup button, continuation explanation | Provide clear unavailable-link state; preserve minimal public disclosure. |
| Expense history `/groups/{id}/expenses` | Description links, payer/date, amount | Search/category/date filters exist in the API but have no UI controls. No pagination. Direct route is not linked from the dashboard heading. |
| Expense detail `/expenses/{id}` | Description heading, date/mode/amount/payer, shares, receipt lines if present, creator edit form, collapsed delete action | Add category/source labels and item payees; improve long descriptions, read/edit separation and destructive-action styling. |
| Categories `/groups/{id}/categories` | Seven default cards, custom rename/delete forms, new-category form | Repeated tall cards and generic Name labels are cumbersome; use a compact layout with contextual accessible names. |
| Receipt `/groups/{id}/receipts` | Upload/status, description/date/total/mode, participants, dynamic line fieldsets, sum/error, approval, extracted text disclosure | No image preview; no per-person allocation preview; no category/tag controls. Long forms and multi-selects need mobile treatment. Keep explicit review/approval. |
| Voice `/groups/{id}/voice` | Record/stop/status, editable transcript, parse button, warnings, expense form and required approval checkbox | Add duration/progress treatment, clearer recording/processing states and concise privacy copy. Preserve typed transcript fallback and approval reset. |
| My balances `/balances` | Cross-group pairwise totals involving caller | No group breakdown or direct settle link; amounts may net across groups while actual claims remain group-specific. |
| Group balances `/groups/{id}/balances` | Pairwise debt rows and back link | Distinguish own debts from all group debts; same rows appear in dashboard. |
| Settle up `/groups/{id}/settlements` | Claim history with status/note and receiver/payer actions; payment form | No outstanding-debt picker/prefill, pending filter, timestamps or pagination. Receiver list includes members without eligible debt; service rejects invalid claims. |
| Suggested settlements `/groups/{id}/simplified` | Minimum-transfer list, explanation and settle-up link | Display-only suggestions can differ from claimable pairwise debts; keep this distinction prominent. |
| Activity `/groups/{id}/activity` | Actor/action/date cards, before/after disclosure, previous/next | Friendly action labels and human dates; structured receipt/category/invite details are incomplete in HTML although raw audit JSON is richer. |
| Insights `/groups/{id}/insights` | Month picker, group/share/paid cards, category totals, twelve monthly totals, selected/all-date CSV downloads | Lists are the current analytics display. Reference can define charts, month labels, spacing and export placement. Preserve numeric text equivalents and exact totals. |
| Reminders `/groups/{id}/nudges` | Explanation, payment-claims link, labelled readonly textareas, copy/share controls and status, empty state | Keep reminders user-initiated; add clear pending-payment context and refresh guidance. Share depends on browser/device support. |
| Validation error `error.html` | Error heading/list and groups link | Generic copy says a change could not be saved even on report GET failures; loses form context. 403/404 from endpoint decorator return JSON even to HTML clients. |

CSV download and `/health` are responses rather than pages. POST/PATCH/DELETE
routes are actions, not additional screens. QR is a generated SVG response.

## Shared component baseline

| Component | Existing implementation | Next design decisions |
|---|---|---|
| App shell | `base.html`, brand/tagline, authenticated or public nav, main, footer | Active state, group context, breadcrumb/back pattern, page titles and skip link. |
| Typography | System font; h1 32–56px, hero 48–82px; small uppercase eyebrows | Define consistent scale, wrapping, readable helper text and less dominant page headers. |
| Colours | Green primary `#14684e`, dark text `#18332e`, muted `#577269`, pale background `#f7faf8`, border `#dce7e1` | Define semantic success/warning/error/pending colours; measure contrast in final design. |
| Cards/layout | White cards, 12px radius, 26px padding; fluid grid, 1.65:1 columns | Consistent density, mobile order, spacing scale and responsive section layouts. |
| Buttons/links | Filled primary and outlined secondary; text links for navigation | Distinguish destructive actions, active/disabled/loading states; avoid many equally weighted actions. |
| Forms | Django `as_p`, full-width inputs/selects, help/error lists, native multi-select | Visible required/optional markers, decimal keyboard hints, participant checkboxes/chips, inline validation and split-total preview. |
| Money rows | Flex rows with labels and amounts; flexible wrapping | Exact two-decimal INR formatting, tabular numerals, protected amount column and long-string tests. Existing API whole-rupee numbers remain valid. |
| Feedback | Django messages; receipt/voice/reminder status and alert regions | Standard success/error placement; common loading and retry language; form-state preservation. |
| Responsive rules | Header stacks and columns collapse at 760px; grid uses minimum 240px cards | Validate 320/390/760/1024/1440px, touch targets, long usernames, long amounts and mobile keyboard behaviour. |
| Shared partials | Expense rows, balance rows, member rows | Keep reusable components rather than duplicating markup per page. |

## Findings to resolve

Priority describes redesign/readiness impact. These are documented findings,
not changes silently added to Phase 7.

| ID | Priority | Finding and evidence | Recommended outcome |
|---|---|---|---|
| F1 | High · functional | Locked plan includes role promotion/demotion, removal, leaving and zero-balance group deletion. `groups/services.py`, routes and templates implement creation/addition/invites, but none of these lifecycle operations. | Resolve the plan/implementation gap before claiming all locked features complete. Enforce group lock, zero-balance and last-admin rules in services as well as UI. |
| F2 | High · recovery | HTML access/missing-resource failures return JSON; non-auth forms often redirect invalid inputs to generic `error.html` without restoring values. | Dedicated 403/404/expired-invite pages; bound forms with inline errors and preserved input. |
| F3 | High · mobile workflow | Dashboard DOM order places all balance/history/member content before the expense form when columns collapse. | Put the primary expense action near the heading and define an intentional mobile content order. |
| F4 | Medium · navigation | Group sections are inline links on only the dashboard; no active section indicator; expense-history/member standalone pages are weakly surfaced. | Reusable group section navigation and consistent back/breadcrumb behaviour. |
| F5 | Medium · scale | Expense history, dashboard history, settlements and invite list load without pagination. Activity alone is paginated. | Pagination/limits and useful filters while preserving stable sorting and access scope. |
| F6 | Medium · forms | Native participant/item multi-selects are difficult on touch devices; no live exact-share sum or receipt payee-allocation preview. | Accessible participant controls and exact-paise preview with clear remaining amount. |
| F7 | Medium · settlement clarity | Settlement form does not show claimable debts/pending reservations; overall balances lack group breakdown. | Show current debt, pending and available amounts in the group where the claim will be recorded. |
| F8 | Medium · semantic completeness | Expense detail omits category/source display and receipt item payees; receipt review omits category/tag controls; activity HTML omits some recorded metadata. | Expose the relevant existing metadata with clear labels; preserve creator-only editing. |
| F9 | Medium · accessibility | No skip link or explicit active navigation; most titles fall back to the brand. Shared focus styling covers inputs/selects but button/link focus is browser-default. | Page-specific titles, skip link, focus-visible treatment and keyboard/screen-reader review. Current Phase 7 pages have descriptive titles. |
| F10 | Medium · visual consistency | Legacy pages mix whole/fractional amounts and secondary controls for destructive actions; repeated full-height cards and long text-heavy headers reduce scanability. | Shared money, status, action and spacing components matched to the reference. |
| F11 | Low · copy | Landing page claims every expense is split equally; implementation supports subsets, unequal amounts, receipts and voice. Some helper copy explains implementation details. | Update feature copy and move technical details out of primary workflows. |
| F12 | Verification | Responsive visual review is complete for the 21 page states listed below. Real-device share/clipboard and keyboard behaviour, all role/empty/provider-error variants and full transaction flows remain outside this visual pass. | Run the acceptance matrix below after the reference is implemented, including real-device checks. |

## Reference-led implementation order

1. Match app shell, typography, colours, spacing, card and button primitives.
2. Establish group navigation and dashboard hierarchy on desktop and phone.
3. Define expense entry/detail/history and participant/split controls.
4. Apply the same patterns to receipt review, voice review and settlement claims.
5. Finish insights/reminders, invites, members, categories, balances and activity.
6. Finish authentication, landing, empty/loading/success and recovery screens.
7. Resolve functional gap F1 explicitly; a visual redesign alone cannot supply it.

Before implementation, map each reference screenshot to a page and viewport,
identify which components are shared, and identify where the reference has no
equivalent for an existing feature. Keep permissions, review approval, exact-paise
splits and receiver-confirmed settlement behaviour intact.

## Acceptance matrix for the redesigned UI

- Each inventory page: desktop and 390px phone, meaningful page title, one primary
  heading, navigation/back route, labels, tab order and visible focus.
- Content states: no groups/expenses/debts; long names/descriptions; fractional
  amounts; many rows; custom categories; admin/member/creator/noncreator views.
- Expense flows: equal/subset/exact shares, payer outside participants, invalid
  totals, successful save/edit/delete and retained validation input.
- Receipt/voice: missing permission/provider failure/invalid upload, loading,
  corrections, participant changes and explicit approval; never save a draft.
- Settlements: partial/full claim, reserved amount, receiver confirm/reject and
  payer cancel; balances change only on confirmation.
- Insights: empty month, year transition, edited/deleted/backdated expenses,
  exact category/month totals; selected/all-date CSV, Unicode/quotes/formula text.
- Reminders: no debts, partial/full pending claims, copy fallback, supported
  share sheet and cancellation; sharing occurs only after the user initiates it.
- Invites/errors: active/expired/revoked, signup/login continuation, unavailable
  resources, forbidden actions and CSRF failures.

## Code map for the redesign

`templates/base.html` and `static/css/main.css` own the shell and visual language.
Each domain has templates under its matching folder. Browser behaviour is in
`static/js/expenses.js`, `receipts.js`, `voice.js` and `insights.js`. Business rules remain in the
domain services. Route wiring is in `config/urls.py`. Phase 7 report/export/nudge
logic is in `apps/insights/services.py`, with thin response views alongside it.

The page-structure regression test lives in
`apps/insights/tests/test_page_audit.py`; Phase 7 business/endpoint tests are in
`apps/insights/tests/test_insights.py`.
