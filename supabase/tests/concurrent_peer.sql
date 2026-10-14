-- LOCAL TEST ONLY. Second session for the concurrent double-submit check in checks.sql, which
-- starts it in the background (psql \!) while its own booking is still uncommitted.
-- Runs harness.peer.sql as user harness.peer.sub and stores 'ok' or 'SQLSTATE: message' in
-- harness.peer.result. Never run this against Supabase.

\set ON_ERROR_STOP on
\set VERBOSITY terse
\o /dev/null
\c :db
set application_name = 'pc_harness_peer';

begin;
select sub, sql from harness.peer \gset peer_
select harness.login(:'peer_sub');
set local role authenticated;
select harness.attempt(:'peer_sql') as outcome \gset peer_
reset role;
update harness.peer set result = :'peer_outcome';
commit;
