# PrimeCare database (Supabase)

| path | purpose |
|---|---|
| `migrations/0001_init.sql` | Tables, RLS policies, grants, RPC functions and seed data. The only file deployed. |
| `tests/` | Local verification harness (auth stub + checks). **Never run against Supabase.** |

## Apply the migration (Supabase SQL Editor)

1. Open your project in the Supabase Dashboard, then go to **SQL Editor** and click **New query**.
2. Paste the whole of `migrations/0001_init.sql` and click **Run**. It runs in one transaction,
   so it either applies completely or not at all.
3. Check it worked: **Table Editor** should list `doctors` (4 rows), `time_slots` (9 rows),
   `patients`, `appointments` and `daily_token_counters`, each marked RLS enabled.

You can safely run it again: it uses `if not exists`, `create or replace`,
`drop policy if exists` and `on conflict do nothing`, and it leaves the `auth` schema alone.
Running it again does not change tables that already exist. If you change a column, write a new
migration for it.

### What it enforces

- **anon** (signed-out API key) gets no table privileges and cannot execute any function.
- **authenticated** can read active doctors and every time slot. It can read, insert and update
  only its own `patients` row, and can read only its own `appointments`. Bookings go through
  `book_appointment()`; inserting, updating or deleting appointment rows directly is not allowed.
- `daily_token_counters` has no grants and no policies. Only `book_appointment()` touches it.
- A patient can hold only one active upcoming appointment (`waiting` or `in_consultation`, dated
  today or later). `book_appointment()` refuses a second one with PC400 (`You already have an
  upcoming appointment.`), and past-dated appointments never block. It locks the caller's
  `patients` row first, so two simultaneous bookings by the same patient cannot both succeed.
- **service_role** grants are revoked too. The app never uses that key, so a leaked key cannot
  read patient data through the Data API.
- Every function pins `search_path = ''` and uses fully qualified names.
- `available_slots`, `book_appointment` and `queue_snapshot` are `SECURITY DEFINER`. Each one
  checks `auth.uid()` itself and returns only slots, tokens or counts. The Supabase Security
  Advisor flags definer functions that authenticated users can execute. Here that is by design.

Errors raised by the functions (the backend maps them to HTTP status codes):

| SQLSTATE | meaning |
|---|---|
| `PC401` | not signed in |
| `PC412` | patient details missing |
| `PC400` | invalid input, or the patient already has an upcoming appointment; the message is safe to show to the user |
| `PC404` | appointment not found, or it belongs to someone else |
| `PC409` | the slot was booked first by someone else |

"Today" means today in the `Australia/Sydney` time zone, as returned by `public.clinic_today()`.

## Auth settings (Supabase Dashboard)

This POC holds synthetic data only and runs locally, so it does not need email confirmation.
New hosted projects have it switched on.

1. Go to **Authentication** -> **Sign In / Providers** -> **Email**.
2. Turn **Confirm email** off and save. "Create an account" then signs the new user straight in.

If you leave **Confirm email** on, registering only shows the message "Check your email to
confirm your account, then log in", and logging in fails with "Invalid email or password" until
the link is clicked. In that case also:

- set **Authentication** -> **URL Configuration** -> **Site URL** to `http://127.0.0.1:5173`.
  Otherwise the link in the email opens the default `http://localhost:3000`, where nothing runs.
- configure custom SMTP (**Authentication** -> **Emails** -> **SMTP Settings**). The built-in
  mailer is heavily rate-limited and only sends to members of the project's organisation.

## Local verification harness

`tests/run_checks.sh <postgres-url>` does the following on a **plain, throwaway** Postgres 15+
server (connect as a superuser):

1. Creates a temporary database.
2. Applies `tests/auth_stub.sql`, which provides the Supabase roles, `auth.users`, `auth.uid()`
   and Supabase's default grants.
3. Applies the migration **twice**, to prove it can be re-run.
4. Runs `tests/checks.sql`, which tests RLS isolation, grants, every error code, token
   sequencing and formatting, slot filtering, the one-upcoming-appointment rule,
   `current_appointment` and the queue maths. For the concurrent double-submit check it starts a
   second psql session (`tests/concurrent_peer.sql`, via psql `\!`). That session uses the same
   psql binary, URL and `PGPASSWORD`/`PGPASSFILE`, so the password must come from one of those,
   not from a prompt.
5. Drops the temporary database.

The script stops at the first failure and exits non-zero. It refuses `*.supabase.co` URLs, and
the stub refuses any database that has the `supabase_admin` role.

One way to get a throwaway server without installing anything system-wide (uses `uv` and the
`pgserver` wheel, which bundles the Postgres binaries):

```bash
D=$(mktemp -d)                                    # everything lives here; delete it afterwards
uv venv "$D/venv" --python 3.12 && uv pip install --python "$D/venv" pgserver
BIN=$("$D/venv/bin/python" -c 'import pgserver._commands as c; print(c.POSTGRES_BIN_PATH)')
(umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$D/pw")
"$BIN/initdb" -D "$D/data" -U postgres --auth=scram-sha-256 --pwfile="$D/pw" >/dev/null
"$BIN/pg_ctl" -D "$D/data" -l "$D/log" -w -o "-h 127.0.0.1 -p 54329 -k ''" start

PGPASSWORD=$(cat "$D/pw") PSQL="$BIN/psql" \
  supabase/tests/run_checks.sh postgresql://postgres@127.0.0.1:54329/postgres

"$BIN/pg_ctl" -D "$D/data" -m fast -w stop && rm -rf "$D"
```

A passing run ends with `ALL CHECKS PASSED` and a `summary: N passed` line. Any Postgres you
control works the same way, for example a Docker `postgres:17` container on 127.0.0.1.
