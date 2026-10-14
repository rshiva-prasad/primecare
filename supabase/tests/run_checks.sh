#!/usr/bin/env bash
# Local verification harness for supabase/migrations/0001_init.sql (never run against Supabase).
#
# Usage: supabase/tests/run_checks.sh <postgres-connection-url>
#   e.g. supabase/tests/run_checks.sh postgresql://postgres@127.0.0.1:54329/postgres
#   PSQL=/path/to/psql overrides the psql binary; pass a password via PGPASSWORD/PGPASSFILE.
#
# Creates a throwaway database on that server, applies auth_stub.sql, applies the migration
# twice (proves it is re-runnable), runs checks.sql, then drops the database. Exits non-zero
# on the first failed assertion or SQL error. checks.sql also starts a second psql session
# (concurrent_peer.sql) with the same psql binary, URL and PGPASSWORD/PGPASSFILE.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <postgres-connection-url>" >&2
  exit 2
fi

url=$1
psql_bin=${PSQL:-psql}
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
migration="$here/../migrations/0001_init.sql"

case $url in
  *supabase.co* | *supabase.com*)
    echo "refusing to run against a hosted Supabase database; use a throwaway local Postgres" >&2
    exit 2
    ;;
esac

db="pc_harness_$(date +%s)_$$"
log=$(mktemp)
peer_log=$(mktemp)
psql_cmd=("$psql_bin" -X -q -v ON_ERROR_STOP=1 -v VERBOSITY=terse)

cleanup() {
  "${psql_cmd[@]}" "$url" -c "drop database if exists $db with (force)" >/dev/null 2>&1 ||
    echo "warning: could not drop throwaway database $db" >&2
  if [[ -s $peer_log ]]; then
    echo "output of the second psql session (concurrent_peer.sql):" >&2
    cat "$peer_log" >&2
  fi
  rm -f "$log" "$peer_log"
}
trap cleanup EXIT

# Read by the \! line in checks.sql that starts the second session.
export PC_HARNESS_PSQL=$psql_bin PC_HARNESS_URL=$url PC_HARNESS_DB=$db \
  PC_HARNESS_PEER_SQL="$here/concurrent_peer.sql" PC_HARNESS_PEER_LOG=$peer_log

"${psql_cmd[@]}" "$url" -c "create database $db"

# \c reuses host/port/user from the original connection and switches to the throwaway database.
"${psql_cmd[@]}" "$url" \
  -v db="$db" -v stub="$here/auth_stub.sql" -v migration="$migration" -v checks="$here/checks.sql" \
  -v peer_ready=1 \
  2>&1 <<'SQL' | tee "$log"
\c :db
set client_min_messages = warning;
\echo '== applying auth_stub.sql'
\i :stub
\echo '== applying 0001_init.sql (first run)'
\i :migration
\echo '== applying 0001_init.sql (second run, must be idempotent)'
\i :migration
reset client_min_messages;
\i :checks
SQL

passed=$(grep -c 'ok - ' "$log" || true)
skipped=$(grep -c 'skip - ' "$log" || true)
if ! grep -q '^ALL CHECKS PASSED$' "$log"; then
  echo "checks did not complete" >&2
  exit 1
fi
echo "summary: $passed passed, $skipped skipped, 0 failed"
