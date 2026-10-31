# Mobile direction: The good-times ledger

The first studies were rejected for weak page structure, excess empty space and
flat presentation. This pass redesigns the information architecture, rather than
recolouring the desktop dashboard. The review target is a 390 × 844 CSS-pixel phone.

## Product point of view

BroYouOweMe is the shared tab for friends, flatmates and trips. Opening the app
should answer: where do I stand, which group needs me, and how do I add this bill?
Group photographs and illustrated people make it feel social. Exact amounts and
explicit settlement states keep the ledger credible.

## References researched

- [Tricount](https://www.tricount.com/): group-first expense journeys and a clear
  sequence from recording bills to resolving balances.
- [Monzo Pots](https://monzo.com/features/pots): visually identifiable spaces for
  different parts of life, with contextual photographs.
- [Splitwise Pro](https://www.splitwise.com/pro): receipt allocation and expense
  search as part of everyday shared spending.
- The owner's original Nesil Noble and Design by Ency examples remain useful for
  personality and typographic confidence, rather than the page architecture.

These are source references, not claims of matching their current native apps.

## Tokens and structure

- Ink `#202b40`; cobalt `#3548d6`; canvas `#f5f6fa`; butter `#fff0bd`;
  melon `#ff976c`; white `#ffffff`.
- Space Grotesk for concise headings and amounts, Plus Jakarta Sans for controls,
  lists and explanatory text. Tabular money. No large marketing hero in the app.
- Variable corner radii: group image 24px, grouped rows 18px, chips 100px.
- Main surfaces use restrained depth; imagery and a strong blue balance surface
  carry the visual emphasis. Smaller separators organise dense expense rows.
- Left-aligned content; 20px phone gutters; a compact top bar; persistent bottom
  navigation and a central Add action; explicit back navigation inside flows.

```text
Home                  Group                 Add bill
brand / profile       photo / back / menu   close / group
hello / balance       group / people        amount
needs your review     balance / actions     description
your groups           expenses/balances     payer / category
photo-led group       date / expense rows   people + split
compact other group   recent bills          share validation
bottom nav + Add      bottom nav + Add      sticky Save
```

Self-critique before building: another grid of equally weighted cards would
repeat the first pass. Use one photographic group, list rows with purposeful
category marks, a compact actionable pending strip, and an amount-first composer.
Avoid a decorative chart on Home; charts belong to Insights and must reconcile.

## Prototype scope

Home, group expenses and balances, amount-first expense composition, expense
detail, settlement review, receipt allocation review, spending insights, activity,
and group utilities. Sample amounts and balances are derived from one in-memory
ledger. Reload resets the prototype. No network write, upload, recording, payment
or messaging is performed. A receipt is a fixed fictional review example.

The prototype demonstrates only the current-user view. Admin/member/creator
permissions, error handling, full authentication and all 21 audited page states
remain application acceptance work after selecting the design.
