# Demo video

## Try the hosted demo

**Live app:** `<render-app-url>` (replace with the actual Render URL after deployment). **Login:** `<render-app-url>/login`. See [publishing instructions](SETUP.md#publish-on-render).

No signup is needed. All three public demo accounts use password **`BroYouOweMeDemo2026!`**:

| Username | Role in the walkthrough |
|---|---|
| `reviewer_mohit` | Group admin and dinner payer; confirms received payments |
| `reviewer_rahul` | Owes Mohit INR 400; records the payment claim |
| `reviewer_ankit` | Owes Mohit INR 400; shows the remaining debt |

1. Log in as `reviewer_mohit`, open **Goa Trip (Demo)**, and inspect **Dinner at Goa**, already seeded for INR 1,200 split equally across the three members. Each share is INR 400. Do not add the same dinner again unless you want another expense.
2. Explore balances, suggested transfers, monthly insights, CSV export and the activity history. Initially Rahul and Ankit each owe Mohit INR 400.
3. Log out and sign in as `reviewer_rahul` (or use a separate browser profile). Record a payment claim of INR 400 to `reviewer_mohit`. The claim is pending and does not clear the debt yet.
4. Switch back to `reviewer_mohit` and confirm the received payment. Rahul's debt clears; Ankit still owes INR 400. Check the activity history for the confirmation.
5. As Mohit, try creating an invite link/QR code, opening receipt review, or adding a new expense. Voice needs configured provider keys; microphone recording also needs browser permission. Review any OCR or voice draft before saving.

These are shared public accounts with dummy data. Other reviewers can change the group, so balances may differ from the initial example. Restarts preserve changes. To replay the example exactly, use Mohit's account to create another group, add `reviewer_rahul` and `reviewer_ankit` by username, and record a fresh INR 1,200 dinner. Avoid entering personal data or real receipts in the shared demo. No real payment is transferred.

The hosted seed reproduces the video's starting three-person dinner scenario; it does not copy local users, sessions or recording overlays. Deployment uses `python manage.py seed_demo --reviewer` with the documented password in `DEMO_PASSWORD`.

## Watch the recording

[Watch the demo on YouTube](https://youtu.be/lcuZM38lUzQ)

The demo is available as an unlisted YouTube video. Open the link above to watch directly without downloading a repository file.

## What it shows

| Time | Step |
|---|---|
| 00:00 | Landing page and private group dashboard |
| 00:10 | Goa Trip with Mohit, Rahul and Ankit |
| 00:17 | Record INR 1,200 for dinner, paid by Mohit |
| 00:28 | Check the three explicit shares of INR 400 |
| 00:33 | Rahul and Ankit each owe Mohit INR 400 |
| 00:39 | Suggested transfers |
| 00:45 | Rahul records a payment claim for INR 400 |
| 00:52 | Claim waits for receiver confirmation |
| 00:58 | Mohit reviews and confirms the payment |
| 01:08 | Rahul's debt is cleared; Ankit still owes INR 400 |
| 01:14 | Monthly insights and CSV export option |
| 01:20 | Activity history |
| 01:25 | Create an invite link and QR code |
| 01:33 | Receipt review screen |
| 01:38 | Voice review screen |

The expense and payment operations are real app interactions using dummy accounts in an isolated local PostgreSQL database. The three accounts and group were prepared before recording. Account switches happen between scenes using authenticated requests. Captions were added to the recording browser; application files were not changed.

The video shows the receipt and voice review interfaces. It does not demonstrate a live OCR upload, microphone recording or provider response. The automated checks and their limits are listed in [VALIDATION.md](VALIDATION.md).

## Repeat the main flow

1. Create accounts for three friends and a group containing all three.
2. Record an INR 1,200 dinner paid by the first friend, split equally.
3. Check that each of the other two owes the payer INR 400.
4. As the second friend, claim a payment of INR 400 to the first.
5. Check that the claim is pending and the balance is unchanged.
6. As the receiver, confirm it. The second friend's debt should disappear.

The same flow is included in the [Postman collection](POSTMAN.md).

## Attach to the submission

Paste [the unlisted YouTube demo link](https://youtu.be/lcuZM38lUzQ) into the submission platform's demo video field. Reviewers can watch directly using the link.
