# Postman collection

Import both files into Postman:

- [BroYouOweMe.postman_collection.json](BroYouOweMe.postman_collection.json)
- [BroYouOweMe.local.postman_environment.json](BroYouOweMe.local.postman_environment.json)

Start the app and select **BroYouOweMe Local**. `base_url` defaults to `http://127.0.0.1:8000`, with no trailing slash. For local HTTP, use debug mode so session and CSRF cookies do not require HTTPS.

## Run the submission flow

Open the Collection Runner, select only **01 Automated submission flow**, and run every request in order with one iteration. Use Postman's desktop app or Desktop Agent for localhost access. Keep the cookie jar enabled.

The 46 requests create three uniquely named accounts, create Goa Trip, add its members, record the INR 1,200 dinner, and check that the two other members owe INR 400 each. They also exercise categories, invites and QR codes, unequal splits, edits, soft deletion, permission checks, overpayment rejection, payment confirmation, reports, CSV export and activity history.

The flow checks that a pending claim leaves the balance unchanged, confirmation clears Rahul's debt, and a second confirmation is rejected. It ends by logging out and checking that private group access requires a session.

Every run creates real records. Use a disposable database. Unique names allow reruns without resetting accounts; previous runs remain in that database. The shared demo password is only for these local test accounts. No real provider keys, database credentials or exported sessions are included.

## CSRF and session handling

The first login-page GET obtains a CSRF cookie. Signup and login establish a session and rotate that cookie. Collection scripts read the current token and attach `X-CSRFToken` to unsafe requests. Postman's cookie jar sends `sessionid` and `csrftoken` automatically. IDs and generated account names are captured as collection variables.

A stale environment variable can override a captured collection variable. The supplied environment contains only `base_url`. Do not add copies of generated IDs or tokens there. After a CSRF failure, rerun the login-page GET and login request. On an HTTPS deployment, use its HTTPS base URL and configure the host's trusted origins.

## Run from a terminal

With Node.js and npm installed:

```powershell
npx --yes newman run BroYouOweMe.postman_collection.json --folder "01 Automated submission flow" --environment BroYouOweMe.local.postman_environment.json
```

To use another host, append `--env-var "base_url=https://your-host.example"`. Avoid production data. The automated folder needs no OCR or voice provider credentials.

## Manual examples

**02 Manual examples (run individually)** covers role changes, departure, member removal, group deletion, invitation acceptance, cancellation, rejection, receipt uploads, WAV uploads and reviewed AI expenses. Read each request's description before sending it. These are examples with state requirements, not a second automated test suite.

Log in as the correct actor first. Use a fresh pending claim for rejection or cancellation. Use a new active invitation for joining; the automated flow revokes its invite. Removal requires settled balances. Leaving as admin also requires another active admin. Delete a group only after every direct balance is zero.

Choose local files in the multipart receipt and WAV requests. Let Postman set multipart content type and boundary. Receipt parsing needs Tesseract. Typed voice parsing needs Groq; audio parsing needs Sarvam and Groq. Parsing produces drafts only. Review the payload and active participants before sending either reviewed expense example.

The browser-only voice approval route accepts a reviewed HTML form and `approved=yes`; its fields and redirect behavior are described in [API.md](API.md). JSON clients can save a reviewed voice expense through `/expenses`.
