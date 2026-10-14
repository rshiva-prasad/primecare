# PrimeCare Clinic: Digital Queue Management System

Patients create an account, enter their details, book an appointment with a doctor, get a queue token and follow
their place in the queue live. The app is the Assignment 2 PrimeCare MVP (five React screens on mock data) made
real: a **React** frontend, a **Python (FastAPI)** backend and a **Supabase** (PostgreSQL) database.

| Screen | Route | What it does |
|---|---|---|
| Login | `/login` | Sign in or create an account (Supabase Auth). Returning patients with an upcoming appointment go straight to Queue Status. |
| Patient Details | `/patient-details` | Name, mobile and email, saved to Supabase and pre-filled on the next visit |
| Book Appointment | `/book-appointment` | Doctors and free time slots loaded from Supabase; booking issues a daily queue token (PC-001, PC-002…) |
| Queue Status | `/queue-status` | Token, position, people ahead, estimated wait and now serving; refreshes every 15 seconds |
| Confirmation | `/confirmation` | The booked appointment, plus Log out |

Every screen except Login requires a session.

## Architecture

```
Browser (React 19 + Vite + Tailwind)
   │  relative /api/... calls, session in httpOnly cookies, no keys in the browser
   ▼
FastAPI backend (Python 3.12)            ← holds SUPABASE_URL + publishable key (backend/.env, or Vercel env vars)
   │  every data call carries the patient's own access token
   ▼
Supabase: Auth + PostgreSQL               ← row-level security on every table
```

- **Frontend** (`frontend/`): A2's screens and look, with A2's three reusable components (FormSection,
  ThreeDButton, IconButton). It talks only to the backend, through relative `/api` URLs. Locally, the Vite dev
  server proxies `/api` to the backend, so browser and API share one origin.
- **Backend** (`backend/`): FastAPI with Pydantic validation. `app/gateway.py` is the only module that talks to
  Supabase. Interactive API docs are at `/api/docs` when `APP_ENV=development`.
- **Database** (`supabase/`): one migration creates the tables, row-level security policies, grants, functions and
  seed data (4 doctors, 9 time slots). See [supabase/README.md](supabase/README.md).

## How credentials and patient data are protected

- **No secrets in the frontend.** The browser bundle contains no Supabase URL or key. Credentials live only in
  `backend/.env`, which git ignores (or, when deployed, in Vercel's environment variables); the committed
  `backend/.env.example` has placeholders.
- **No admin key at all.** The backend uses only Supabase's *publishable* key, and refuses to start with a
  secret/service-role key. Each request uses the logged-in patient's own token, so the database's row-level
  security limits every query to that patient's rows.
- **Database-enforced privacy.** Signed-out (anon) access is revoked on every table and function. A patient can
  read and update only their own details and read only their own appointments. Bookings go only through
  `book_appointment()`, which also allows just one upcoming appointment per patient. The queue functions return
  tokens and counts, never other patients' details.
- **Sessions.** Access and refresh tokens are kept in `HttpOnly`, `SameSite=Lax` cookies scoped to `/api`, and
  marked `Secure` unless `COOKIE_SECURE=false` (set only for local http). Nothing is stored in localStorage. Sessions refresh automatically, and
  logout revokes the session on Supabase even if the access token has already expired.
- **Request hygiene.** Requests that change data must be JSON (HTTP 415 otherwise, so cross-site forms are rejected),
  and any request that sends an `Origin` header must come from an allowed origin (HTTP 403 otherwise). Responses carry security headers and `Cache-Control: no-store`. Inputs are validated on the
  server, error messages are generic (no stack traces, and the same "Invalid email or password." whether the
  email or the password is wrong), and logs contain no personal data or tokens.
- **Brute-force throttle.** After 5 failed logins for one email from one IP within 15 minutes, or 20 login/register
  attempts from one IP within 5 minutes, further attempts return HTTP 429. A successful login clears the
  failed-login count.

## Project structure

```
primecare-a3/
├── frontend/                 React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── pages/            the five screens (+ tests)
│       ├── components/       FormSection, ThreeDButton, ui/IconButton, SessionBar, states
│       ├── auth/             AuthProvider, ProtectedRoute, PostLoginRedirect, hooks
│       ├── lib/              api.ts (typed API client), validation, forms
│       └── hooks/            useApiData (loading/error/polling)
├── backend/                  FastAPI (pipenv)
│   ├── app/                  main, config, gateway, deps, cookies, errors, schemas, presenters, throttle, routers/
│   ├── tests/                pytest suite (fake Supabase gateway, no network)
│   ├── Pipfile, Pipfile.lock dependencies (Vercel installs the [packages] from Pipfile.lock)
│   ├── ruff.toml, pytest.ini, mypy.ini, .coveragerc   tool settings (no pyproject.toml: see Deploying to Vercel)
│   └── .env.example          placeholders only; copy to .env
├── supabase/
│   ├── migrations/0001_init.sql   the database: run this in the Supabase SQL Editor
│   └── tests/                local-only verification harness (never run on Supabase)
├── docs/PROMPTS.md           prompt log (assignment appendix)
├── vercel.json               Vercel deployment: frontend + backend services, routing, security headers
├── .vercelignore             keeps .env files out of Vercel CLI uploads
└── .gitignore                ignores .env files, venvs, node_modules, builds, caches, .vercel/
```

## Running locally

**Prerequisites:** Python 3.12.13 (the exact version pinned in `backend/Pipfile`; pipenv offers to install it if pyenv
or asdf is present) with [pipenv](https://pipenv.pypa.io/), Node.js 22.13+ or 24+ with npm, and a Supabase project.

1. **Supabase**
   1. In the SQL Editor, run `supabase/migrations/0001_init.sql`.
   2. Under Authentication → Sign In / Providers → Email, turn off **Confirm email**. This app holds synthetic data
      only.
   3. Full details are in [supabase/README.md](supabase/README.md).
2. **Backend**
   ```bash
   cd backend
   cp .env.example .env        # set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY (never the secret key)
   pipenv install --dev
   pipenv run dev              # http://127.0.0.1:8000  (API docs: /api/docs)
   ```
3. **Frontend** (in a second terminal)
   ```bash
   cd frontend
   npm install
   npm run dev                 # http://127.0.0.1:5173
   ```

Open http://127.0.0.1:5173 and create an account. Both servers listen on 127.0.0.1 only.

### Configuration (`backend/.env`)

On Vercel the same settings are project environment variables (see [Deploying to Vercel](#deploying-to-vercel)).

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | Publishable (`sb_publishable_…`) or legacy anon key. Never the secret/service-role key. |
| `APP_ENV` | `development` turns on `/api/docs`; `production` (the default) hides it |
| `COOKIE_SECURE` | `true` (the default) marks the session cookies `Secure`; set `false` only for local http |
| `ALLOWED_ORIGINS` | Comma-separated origins accepted in a request's `Origin` header (default `http://127.0.0.1:5173,http://localhost:5173`); any other origin gets 403 |
| `SUPABASE_TIMEOUT_SECONDS` | Upstream timeout (default 10) |
| `AUTH_THROTTLE_ENABLED` | Login/register throttle (default `true`) |
| `TRUSTED_CLIENT_IP_HEADER` | Header the throttle reads the client IP from, instead of the connecting address. Leave unset locally; on Vercel set `x-vercel-forwarded-for`, which Vercel overwrites so clients cannot fake it. Never set it to a header clients can send unchanged. |

## Deploying to Vercel

`vercel.json` deploys both halves as one Vercel project using Vercel Services (beta): the React build as static
files and FastAPI as a Python function, on the same domain. The browser keeps calling relative `/api` URLs, so
there is no CORS and the session cookies stay first-party.

| Request | Served by |
|---|---|
| `/api/*` | `backend/`: the FastAPI app (`app.main:app`) on Python 3.12, installed from `Pipfile.lock` |
| Everything else | `frontend/`: the Vite build; unknown paths fall back to `index.html` so the React routes work |

Frontend responses carry a strict Content-Security-Policy (the app's own origin only, no framing) and the other
security headers; hashed files under `/assets/` are cached for a year. API responses keep the backend's own headers.
Tests, caches and `.env` files are left out of the function bundle.

1. In Vercel, add a new project and import this GitHub repository. Keep the root directory at the repository root,
   where `vercel.json` is.
2. Under **Settings → Environment Variables**, add these for **Production**:

   | Variable | Value |
   |---|---|
   | `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
   | `SUPABASE_PUBLISHABLE_KEY` | The publishable key, never the secret key |
   | `ALLOWED_ORIGINS` | The production URL, e.g. `https://<project>.vercel.app` (no trailing slash) |
   | `TRUSTED_CLIENT_IP_HEADER` | `x-vercel-forwarded-for` |

   Leave `APP_ENV` and `COOKIE_SECURE` unset: their defaults (`production`, `true`) hide the API docs and mark the
   cookies `Secure`.
3. Deploy, then open `https://<project>.vercel.app/api/health`. It should return
   `{"status":"ok","supabase_configured":true}`. Create a test account to check the full flow.

Notes:

- **Preview deployments get their own URLs**, which are not in `ALLOWED_ORIGINS`, so logging in on a preview returns
  403. Test on the production URL, or add the preview URL to `ALLOWED_ORIGINS`. Environment variable changes apply
  only to new deployments, so redeploy after changing one.
- **Deploy through GitHub.** If you use the Vercel CLI instead, `.vercelignore` stops it uploading `.env` files (the
  CLI does not read `.gitignore`).
- **Why there is no `backend/pyproject.toml`:** Vercel's Python builder treats a `pyproject.toml` as the dependency
  list ahead of `Pipfile.lock`, and a tool-settings-only file made the build fail. The tool settings live in
  `ruff.toml`, `pytest.ini`, `mypy.ini` and `.coveragerc` instead.
- **Locally, keep using `pipenv run dev` and `npm run dev`.** `vercel dev` does not suit this setup: it serves
  `index.html` for Vite's source files, the CSP blocks Vite's inline refresh script, and it re-syncs `backend/.venv`.

## Tests and checks

| Layer | Commands |
|---|---|
| Backend | `pipenv run test` (pytest, coverage floor 80%), `pipenv run lint`, `pipenv run typecheck`, `pipenv run format` |
| Frontend | `npm run test:coverage` (Vitest + React Testing Library, coverage floor 80%), `npm run lint`, `npm run build`, `npm run format:check` |
| Database | `supabase/tests/run_checks.sh <throwaway-postgres-url>`: row-level security isolation, grants, error codes, booking rules (see [supabase/README.md](supabase/README.md)) |

Backend tests replace Supabase with an in-memory fake, so they need no network or keys.

## API overview

All endpoints are under `/api` and use JSON. Errors are `{"detail": "..."}`; validation errors (422) also include
`"fields": {"<field>": "<message>"}`.

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /api/health` | – | Liveness, and whether Supabase is configured |
| `POST /api/auth/register` | – | Create an account; starts a session |
| `POST /api/auth/login` | – | Log in; sets session cookies |
| `POST /api/auth/logout` | – | End the session (always 204) |
| `GET /api/auth/me` | ✓ | Current user |
| `GET` / `PUT /api/patients/me` | ✓ | Read / save patient details |
| `GET /api/doctors` | ✓ | Doctors, plus the clinic's `today` and `max_date` |
| `GET /api/doctors/{id}/slots?date=YYYY-MM-DD` | ✓ | Free time slots |
| `POST /api/appointments` | ✓ | Book (409 if the slot was just taken, 400 if you already have an upcoming appointment) |
| `GET /api/appointments/current` | ✓ | Your upcoming appointment (404 if none) |
| `GET /api/appointments/current/queue` | ✓ | Your queue position and estimated wait |

## Known limitations

- **One upcoming appointment per patient, and no cancellation.** A2 had no cancel feature, so to demo another
  booking, create a new account.
- **The queue never advances on its own.** There is no staff screen to call the next patient, so the first person
  in line shows as "Now serving" on the day.
- **Clinic time zone:** "today" and past-slot rules use Australia/Sydney, decided by the database.
- **Deactivating a doctor** (only possible directly in the database) hides their existing bookings from patients, but
  those bookings still count as upcoming, so the patient cannot book again (the booking form just reloads).
- **The login throttle is in memory, per server process.** Instances don't share counts. Locally, every request
  arrives through the Vite proxy from 127.0.0.1, so the per-IP limit acts as one limit for everyone, which is fine
  for a single-user demo. On Vercel, `TRUSTED_CLIENT_IP_HEADER` makes each visitor count against their own IP, but
  each function instance keeps its own counts and loses them when it restarts, so the limits are best-effort there.
