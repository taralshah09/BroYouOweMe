# Reference-led UI prototypes

Open `index.html` in a browser. No server, build step or database is needed.
Google Fonts improves the typography when online; local serif/sans-serif fallbacks
keep the previews usable offline.

These are design-review documents with fictional usernames and in-memory examples,
not Django application changes. Reloading resets all preview actions. Existing
application templates, permissions, services and ledger data are untouched.

## Directions

| Direction | Reference and interpretation | Tokens |
|---|---|---|
| A — Shared dreams (`dream.html`) | [Nesil Noble](https://nesilnoble.com/): muted purple, expressive serif headlines, a playful receipt composition. Adapted to a quiet ledger rather than its immersive portfolio interaction. | Purple `#545388`, paper `#eeedf5`, ink `#302d4d`, muted `#69647b`, lavender `#e1dfee`, white `#ffffff`. DM Serif Display for the landing headline; DM Sans for controls and financial data. |
| B — Split studio (`electric.html`) | [Design by Ency](https://www.designbyency.com/): electric blue, pale surfaces, bold condensed typography and rounded controls. Uses alternative fonts; no proprietary font or artwork copied. | Blue `#3030d6`, paper `#f6f7ff`, ink `#16105f`, muted `#565a82`, pale blue `#e6e8fb`, white `#ffffff`. Barlow Condensed for expressive headings; DM Sans for the app. |
| C — The social ledger (`blend.html`, recommended) | A quieter blend: lavender landing, purple balance panel, plain readable dashboard headings, rounded actions and a single playful bill illustration. | Purple `#5149bb`, paper `#f5f4fa`, ink `#24213b`, muted `#646078`, lavender `#e9e5fb`, white `#ffffff`. Barlow Condensed on landing; DM Sans for working screens. |

All layouts use left-aligned working content. Desktop pairs the history and member
area with a balance/settlement rail. Mobile places Add expense above the group
navigation and shows balances before the expense list. Forms keep the split
preview after the fields on phones. There is no scroll-jacking or background audio.

## Reference-to-page mapping

Reference homepages were inspected on 2026-10-30 using their published HTML/style
definitions; a native browser screenshot also confirmed Nesil's purple canvas and
expressive headline. These studies are interpretations, not pixel reproductions.
No mobile reference screenshot or complete reference screenshot set was captured.

| App screen | Shared components / reference cues | Review widths |
|---|---|---|
| Landing | Oversized reference-led headline, pill action, original CSS bill illustration | 320, 390, 760, desktop |
| Group dashboard / history | Shared header, avatar, group navigation, search/filter, protected amount column, balance panel | 320, 390, 760, desktop |
| Add expense | Same shell/buttons; participant checkboxes; equal/exact shares; live integer-paise allocation | 320, 390, 760, desktop |
| Settlement claims | Same panels/forms; distinct pending state and receiver confirmation | 320, 390, 760, desktop |

The comparison selector provides exact 320/390/760px iframe widths. Desktop fills
the available window; resize the window to assess 1024/1440px. These are review
targets, not a claim that all sizes have passed visual verification.

The references have no direct equivalent for receipt correction, voice review,
exact-share validation, debt reservation, membership permissions or receiver-only
confirmation. Those must follow `../UI_AUDIT.md`, `../PLAN.md` and `../SCHEMA.md`.

## Working preview interactions

- Switch between three directions and four screens (plus the history state).
- Search expenses and filter categories.
- Change participants, amount and equal/exact splits. The preview uses integer
  paise and deterministic remainder allocation in mock member-ID order.
- Add an expense to the in-memory list; summary cards remain illustrative.
- Confirm/reject a sample received claim or create a bounded payment claim.
- Receipt, voice, invites and secondary group sections show explanatory preview
  feedback rather than opening operational flows.

Prototype navigation is not proposed production chrome. My groups/My balances
and the back links are review shortcuts, not full implementations of those pages.

## Audit mapping and next implementation pass

The studies demonstrate the intended response to F3 (primary action/mobile order),
F4 (persistent group navigation), F6 (participants and exact shares), F7 (group
debt/pending/available context), F9 (skip link, focus, titles and labels), F10
(money/status/spacing) and F11 (accurate landing copy). This does not close those
findings in the application.

After direction selection, apply the audit's existing implementation order:
shell and tokens; shared group navigation and dashboard hierarchy; expense flows;
receipt/voice/settlements; remaining group pages; authentication and recovery.
Preserve all membership/creator/admin checks, explicit draft review and exact
money handling. F1 needs a separate explicit functional resolution; CSS cannot
implement group lifecycle services. F2/F5/F8 still need their dedicated work.

## Verification

- `node --check docs/prototypes/prototype.js`: passed.
- Existing Django code was not modified; backend tests are not relevant to these
  standalone review documents.
- Full browser and responsive visual verification is pending. The browser access
  host was unavailable, and native UI review was interrupted by user input.
- Final reference screenshot mapping, contrast checks, keyboard review and the
  audit acceptance matrix remain required when integrating the chosen direction.
