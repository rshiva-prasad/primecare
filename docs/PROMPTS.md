# BUS4012 Assignment 03: PrimeCare Clinic Prompt Log

**Application:** PrimeCare Clinic – Digital Queue Management System (React + Python FastAPI + Supabase)
**Live app:** https://primecare-beige.vercel.app
**GitHub repository:** https://github.com/rshiva-prasad/primecare-a3 (private)
**Development environment:** VS Code with an AI coding assistant

## Approach

A3 turns the A2 MVP (five React screens on mock data, with a demo login checked in the browser) into a full-stack
app: React frontend, Python FastAPI backend, Supabase database, hosted on Vercel. Three layers must agree on every
name, data shape and error code, so I worked **plan first, build layer by layer, review, fix, then go live**.

| Stage | Prompts | Goal |
|---|---|---|
| 1. Plan | 1–3 | Gather context, fix the scope, approve a written design |
| 2. Build | 4–6 | Database, backend and frontend, each with its own checks |
| 3. Connect | 7 | Supply Supabase credentials safely |
| 4. Review | 8–11 | Security, cross-layer consistency, user flow, live end-to-end test |
| 5. Fix | 12–13 | Agree fixes across layers, apply, re-test |
| 6. Go live | 14–16 | Run the migration, refine the journey, deploy to Vercel |

---

## Stage 1: Plan

### Prompt 1: Context and requirements

```
Read the assignment brief and all files from my previous assignments (design deck, report, prompt log and
MVP code). List the requirements and the gaps between the MVP and the brief, then propose a plan.
Work locally only and do not commit anything until I approve.
```

- **Purpose:** give the AI full context and set the ground rules before any code.
- **Result:** three gaps found: mock data only; demo credentials checked and shown in the browser (the login flow is
  peer-reviewed); fixed queue numbers, so "live tracking" could never change.

### Prompt 2: Clarifying questions (follow-up)

```
Ask me any questions you need before designing. Keep the scope to exactly what the brief asks, keep the
MVP's visual design, and I will provide the Supabase project details.
```

- **Purpose:** decide scope and design myself rather than let the AI add features.
- **Result:** scope fixed to A2's five screens; extras (staff console, A1 dashboard and QR screens) declined. The
  backend reaches Supabase with the **publishable key plus each patient's own login token**, enforced by row-level
  security, so no service-role (admin) key exists anywhere.

### Prompt 3: Approve the design (follow-up)

```
Approved. Write the design spec as the contract between the layers, scaffold the project, and initialise
git with a .gitignore that excludes every .env file. No commits yet.
```

- **Purpose:** lock a single contract so the layers can be built in parallel.
- **Result:** spec written, A2 frontend copied in, Python 3.12 pipenv backend created; `.env` blocked by git before
  any secret file existed.

---

## Stage 2: Build

### Prompt 4: Database (Supabase migration)

```
Build the database layer from the spec as one Supabase migration: tables, constraints, row-level security
on every table, least-privilege grants, and booking and queue functions with clear error codes. Seed the
reference data. Write tests proving one user cannot see another's data and queue tokens are issued in
order without duplicates, and run them against a local Postgres.
```

- **Purpose:** replace A2's mock data with real, secured tables.
- **Result:** 113 checks passed; 7 deliberately broken copies of the migration each failed, proving the tests catch
  mistakes.

### Prompt 5: Python backend (FastAPI)

```
Build the FastAPI backend from the spec; it is the only layer that talks to Supabase. Use Supabase Auth
with httpOnly session cookies, send each user's own token on every database call, validate all input on
the server, return generic errors, and keep credentials in environment variables with a placeholder
.env.example. Write unit tests with at least 80% coverage and run lint and type checks.
```

- **Purpose:** add the Python layer the brief requires and keep every credential server-side.
- **Result:** 236 tests, 100% coverage; ruff and mypy clean. JSON-only writes plus an Origin check block cross-site
  form forgery; login errors are generic ("Invalid email or password.").

### Prompt 6: React frontend

```
Connect the existing React screens to the backend API, keeping the MVP's look and reusable components.
Remove all mock data and demo credentials, add loading, error and empty states, protect logged-in routes,
and refresh the queue screen automatically. Write tests for every screen.
```

- **Purpose:** make A2's five screens real without changing their design.
- **Result:** 134 tests, 99% coverage; no keys or Supabase URLs in the browser bundle.

| Screen | Change |
|---|---|
| Login | Real sign-in and "Create an account"; demo credentials removed |
| Patient Details | Pre-fills saved details |
| Book Appointment | Loads doctors and free slots from Supabase |
| Queue Status | Refreshes every 15 seconds |
| Confirmation | Shows the real booking; "Back to dashboard" becomes **Log out** |

---

## Stage 3: Connect

### Prompt 7: Supabase credentials

```
I have put the Supabase credentials in backend/.env. Check they are valid without printing them.
```

- **Purpose:** connect the real project without pasting secrets into the chat.
- **Result:** confirmed URL format, publishable (not secret) key, file git-ignored and set owner-only. A read-only
  test reached the project and showed the tables did not exist yet, as expected.

---

## Stage 4: Review

### Prompt 8: Security review

```
Act as a read-only security reviewer for the whole app: database permissions, login and sessions, CSRF,
input validation, error and log leakage, secret handling and dependencies. Report only real,
evidence-backed issues.
```

- **Purpose:** test the login flow and data handling the peer review will grade.
- **Result:** nothing critical. Four issues: no login throttle (SEC-1), one account could book every slot (SEC-2), a
  failed logout looked successful (SEC-3), a build-only npm advisory (SEC-4).

### Prompt 9: Cross-layer consistency

```
Check that the database, backend and frontend agree on every endpoint, field name, response shape and
error code. List any mismatch that would break at runtime.
```

- **Purpose:** catch mismatches each layer's own tests could not see.
- **Result:** all contracts matched. Found the date picker used the browser's date while bookings use Sydney time
  (XL-1/2), and `npm run preview` used an address the backend rejects (XL-3).

### Prompt 10: User flow and A2 parity

```
Walk through the app as a new and a returning user, compare it with the MVP design, and test edge cases:
slot taken, session expiry, page refresh, back button after logout, double submit, keyboard and mobile.
```

- **Purpose:** review the app as an end user, the way peers will.
- **Result:** **FLOW-1 (high):** a patient could book twice and queue "behind themselves". Also: no way back to an
  existing booking, the date issue again, missing sign-up settings in the setup guide, no session-expiry message,
  stale errors, and odd wait wording for future bookings (FLOW-2 to FLOW-7).

### Prompt 11: Live integration test

```
Run the real backend against a local Postgres and a fake Supabase Auth, and test the full journey over
HTTP with two users, including data isolation, logout and CSRF checks. Never load the real .env.
```

- **Purpose:** prove the layers work together, not just in isolation.
- **Result:** 73 passed, 2 failed. **39a** was a real bug (logout after session expiry didn't revoke it). **37e**
  (deactivated doctor's bookings disappear) was out of scope and recorded as a known limitation.

---

## Stage 5: Fix

### Prompt 12: Agreed fixes

```
Confirm each finding is real, decide one fix per issue that every layer follows, and apply the smallest
correct change in each layer. Re-run all tests and report the real results.
```

- **Purpose:** fix issues without breaking the contract between layers.
- **Result:** every confirmed finding except 37e fixed. Tests: 128 database, 274 backend (100%), 145 frontend (99%).
  - One upcoming appointment per patient, safe against simultaneous submissions (FLOW-1, SEC-2)
  - Server supplies the clinic's Sydney date (XL-1/2, FLOW-3)
  - Existing appointment shown instead of a second booking form (FLOW-2)
  - Login throttle returning 429, not fooled by a spoofed `X-Forwarded-For` (SEC-1)
  - Logout revokes the session even when the access cookie has expired (39a)
  - `npm audit fix`: 0 vulnerabilities (SEC-4)

After an agent briefly tried a test login that `pipenv` would have loaded from `backend/.env` (it failed to connect),
every agent ran with `PIPENV_DONT_LOAD_ENV=1`.

### Prompt 13: Re-test (follow-up)

```
Re-run the live integration test. Update only the expectations the fixes changed and do not weaken any
other check.
```

- **Purpose:** verify the fixes end to end.
- **Result:** 89 passed, 0 failed, 1 expected skip (37e). The backend ran from a code-only copy that could not see
  `.env`; a network watcher saw only local connections.

---

## Stage 6: Go live

### Prompt 14: Database deployment

```
Which script should I run in Supabase, and how do I confirm it worked?
```

- **Purpose:** create the tables on the live project without running the local test harness there.
- **Result:** ran `supabase/migrations/0001_init.sql` ("Success. No rows returned"; 4 doctors, 9 slots). Live checks:
  health `ok`; protected endpoint 401 without login; anonymous access to every table and function refused (401,
  while a non-existent function returns 404, proving they exist and are locked).

### Prompt 15: Returning patients

```
Does the brief need a home page for returning users? If not, what is the simplest way to improve their
journey?
```
```
Go with the redirect.
```

- **Purpose:** stop returning patients clicking through Patient Details to reach their booking, without adding a
  screen the brief doesn't ask for.
- **Result:** tests written first, then a post-login redirect: upcoming appointment → Queue Status; otherwise or on
  lookup failure → Patient Details; session expired → login with a message. 150 frontend tests, 99% coverage.

### Prompt 16: Vercel deployment

```
Do we need to deploy this app? If so, write the Vercel configuration to host the frontend and backend
together on one domain.
```

- **Purpose:** meet the brief's live-deployment requirement.
- **Result:** 291 backend tests (17 new), 100% coverage; local `vercel build` and run succeeded.
  - `/api/*` routed to the backend, everything else to the frontend: one domain, no CORS, cookies work as locally
  - Strict Content-Security-Policy and security headers on every page
  - `TRUSTED_CLIENT_IP_HEADER` set to Vercel's own IP header so the login throttle works per visitor
  - Tests and `.env` files excluded from the deployment bundle and CLI uploads

---

## Note on the prompts

Prompts are shown in a generalised form that captures the intent of each step, so the same sequence could be reused
to build a similar app. The results are from the actual build. Prompts 4–6 and 8–13 were issued by the AI assistant
to its helper agents on my behalf; the rest are mine.
