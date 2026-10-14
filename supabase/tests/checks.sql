-- LOCAL TEST ONLY. Behavioural checks for 0001_init.sql, run by run_checks.sh after
-- auth_stub.sql and the migration. Every check prints "ok - ..."; any failure raises and stops psql.
-- A patient can hold only one active upcoming appointment, so every booking scenario has its own
-- user. A, B, C have patient rows (inserted through RLS) and form tomorrow's dr-perera queue.
-- D is signed up but has not entered patient details. E to J get patient rows from the
-- superuser: E double booking, F another date, G past appointments, H token formatting,
-- I today's clock, J concurrent double submit.

\set ON_ERROR_STOP on
\set VERBOSITY terse
\o /dev/null

\set a '00000000-0000-4000-8000-00000000000a'
\set b '00000000-0000-4000-8000-00000000000b'
\set c '00000000-0000-4000-8000-00000000000c'
\set d '00000000-0000-4000-8000-00000000000d'
\set e '00000000-0000-4000-8000-00000000000e'
\set f '00000000-0000-4000-8000-00000000000f'
\set g '00000000-0000-4000-8000-000000000010'
\set h '00000000-0000-4000-8000-000000000011'
\set i '00000000-0000-4000-8000-000000000012'
\set j '00000000-0000-4000-8000-000000000013'
\set already_booked 'You already have an upcoming appointment.'

-- ---------------------------------------------------------------------------------------------
\echo '== harness helpers'
-- ---------------------------------------------------------------------------------------------

create schema harness;
grant usage on schema harness to anon, authenticated;

create function harness.ok(p_cond boolean, p_label text)
returns void
language plpgsql
as $$
begin
  if p_cond is not true then
    raise exception 'FAIL: %', p_label;
  end if;
  raise notice 'ok - %', p_label;
end;
$$;

create function harness.eq(p_actual anycompatible, p_expected anycompatible, p_label text)
returns void
language plpgsql
as $$
begin
  if p_actual is distinct from p_expected then
    raise exception 'FAIL: % (expected %, got %)', p_label, p_expected, p_actual;
  end if;
  raise notice 'ok - %', p_label;
end;
$$;

-- Runs p_sql as the current role and requires it to fail with exactly p_sqlstate and, when
-- p_message is given, exactly that message.
create function harness.expect_error(p_sql text, p_sqlstate text, p_label text,
                                     p_message text default null)
returns void
language plpgsql
as $$
declare
  v_state text;
  v_message text;
begin
  begin
    execute p_sql;
  exception
    when others then
      get stacked diagnostics v_state = returned_sqlstate, v_message = message_text;
      if v_state = p_sqlstate and (p_message is null or v_message = p_message) then
        raise notice 'ok - % [% "%"]', p_label, v_state, v_message;
        return;
      end if;
      raise exception 'FAIL: % (expected % "%", got %: %)',
        p_label, p_sqlstate, coalesce(p_message, '<any message>'), v_state, v_message;
  end;
  raise exception 'FAIL: % (expected SQLSTATE %, but it succeeded)', p_label, p_sqlstate;
end;
$$;

-- Runs p_sql as the current role; returns 'ok', or 'SQLSTATE: message' if it fails.
create function harness.attempt(p_sql text)
returns text
language plpgsql
as $$
declare
  v_state text;
  v_message text;
begin
  execute p_sql;
  return 'ok';
exception
  when others then
    get stacked diagnostics v_state = returned_sqlstate, v_message = message_text;
    return v_state || ': ' || v_message;
end;
$$;

-- Concurrency check: tests/concurrent_peer.sql (a second psql session) runs sql as user sub
-- and stores the attempt() outcome in result.
create table harness.peer (sub uuid not null, sql text not null, result text);

-- Waits until the second session is blocked on a lock ('blocked') or has finished ('finished').
-- Both waits re-read pg_stat_activity and harness.peer, so they also work inside a transaction.
create function harness.wait_for_peer()
returns text
language plpgsql
as $$
declare
  v_deadline timestamptz := clock_timestamp() + interval '20 seconds';
begin
  loop
    perform pg_stat_clear_snapshot();
    if exists (select 1 from harness.peer p where p.result is not null) then
      return 'finished';
    end if;
    if exists (
      select 1 from pg_stat_activity s
      where s.datname = current_database()
        and s.application_name = 'pc_harness_peer'
        and s.wait_event_type = 'Lock'
    ) then
      return 'blocked';
    end if;
    if clock_timestamp() > v_deadline then
      raise exception 'FAIL: the second psql session did not start or got stuck';
    end if;
    perform pg_sleep(0.05);
  end loop;
end;
$$;

-- Waits for the second session to finish and returns its outcome.
create function harness.peer_result()
returns text
language plpgsql
as $$
declare
  v_deadline timestamptz := clock_timestamp() + interval '20 seconds';
  v_result text;
begin
  loop
    select p.result into v_result from harness.peer p where p.result is not null;
    if found then
      return v_result;
    end if;
    if clock_timestamp() > v_deadline then
      raise exception 'FAIL: the second psql session did not report a result';
    end if;
    perform pg_sleep(0.05);
  end loop;
end;
$$;

create function harness.skip(p_label text)
returns void
language plpgsql
as $$
begin
  raise notice 'skip - %', p_label;
end;
$$;

-- Sets (or clears, when null) the JWT claims for the rest of the current transaction.
create function harness.login(p_sub uuid)
returns void
language plpgsql
as $$
begin
  perform set_config(
    'request.jwt.claims',
    case when p_sub is null then ''
         else json_build_object('sub', p_sub, 'role', 'authenticated')::text end,
    true
  );
end;
$$;

-- ---------------------------------------------------------------------------------------------
\echo '== schema, privileges and seed (after applying the migration twice)'
-- ---------------------------------------------------------------------------------------------

select harness.eq(
  (select string_agg(c.relname, ' ' order by c.relname)
   from pg_class c
   where c.relnamespace = 'public'::regnamespace and c.relkind not in ('i', 'I')),
  'appointments daily_token_counters doctors patients time_slots',
  'public contains exactly the five tables (no views or sequences)');

select harness.eq(
  (select count(*)::int from pg_class c
   where c.relnamespace = 'public'::regnamespace and c.relkind = 'r' and not c.relrowsecurity),
  0,
  'RLS is enabled on every public table');

select harness.eq(
  (select string_agg(entry, ' ' order by entry) from (
     select format('%s:%s:%s', c.relname,
                   case when g.grantee = 0 then 'PUBLIC' else g.grantee::regrole::text end,
                   g.privilege_type) as entry
     from pg_class c
     cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) g
     where c.relnamespace = 'public'::regnamespace and c.relkind = 'r'
       and g.grantee <> c.relowner) s),
  'appointments:authenticated:SELECT doctors:authenticated:SELECT '
    || 'patients:authenticated:INSERT patients:authenticated:SELECT '
    || 'patients:authenticated:UPDATE time_slots:authenticated:SELECT',
  'table grants are exactly the least-privilege set (anon, service_role, PUBLIC: none)');

select harness.eq(
  (select string_agg(entry, ' ' order by entry) from (
     select format('%s:%s:%s', p.proname,
                   case when g.grantee = 0 then 'PUBLIC' else g.grantee::regrole::text end,
                   g.privilege_type) as entry
     from pg_proc p
     cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) g
     where p.pronamespace = 'public'::regnamespace and g.grantee <> p.proowner) s),
  'available_slots:authenticated:EXECUTE book_appointment:authenticated:EXECUTE '
    || 'clinic_now_time:authenticated:EXECUTE clinic_today:authenticated:EXECUTE '
    || 'current_appointment:authenticated:EXECUTE queue_snapshot:authenticated:EXECUTE',
  'function EXECUTE grants: authenticated only, six RPCs only');

select harness.eq(
  (select string_agg(p.proname, ' ' order by p.proname) from pg_proc p
   where p.pronamespace = 'public'::regnamespace
     and not coalesce(p.proconfig @> array['search_path=""'], false)),
  null::text,
  'every public function pins search_path to empty');

select harness.eq(
  (select string_agg(p.proname, ' ' order by p.proname) from pg_proc p
   where p.pronamespace = 'public'::regnamespace and p.prosecdef),
  'available_slots book_appointment queue_snapshot',
  'only available_slots, book_appointment and queue_snapshot are SECURITY DEFINER');

select harness.eq(
  (select string_agg(p.proname || ':' || p.provolatile::text, ' ' order by p.proname) from pg_proc p
   where p.pronamespace = 'public'::regnamespace and p.prorettype <> 'trigger'::regtype),
  'available_slots:s book_appointment:v clinic_now_time:s clinic_today:s '
    || 'current_appointment:s queue_snapshot:s',
  'function volatility matches the contract');

select harness.eq(
  pg_get_function_result('public.available_slots(text, date)'::regprocedure),
  'TABLE(slot_time time without time zone, label text)',
  'available_slots returns only slot_time and label');

select harness.eq(
  pg_get_function_result('public.queue_snapshot(uuid)'::regprocedure),
  'TABLE(token text, queue_position integer, total_in_queue integer, '
    || 'now_serving_token text, avg_consult_minutes integer, is_today boolean, status text)',
  'queue_snapshot returns only tokens, counts and flags');

select harness.eq(
  pg_get_function_result('public.clinic_today()'::regprocedure), 'date',
  'clinic_today returns a scalar date (PostgREST sends it as a bare JSON string)');

select harness.eq(
  (select string_agg(format('%s:%s:%s:%s', tablename, policyname, cmd, roles), ' '
                     order by tablename, policyname)
   from pg_policies where schemaname = 'public'),
  'appointments:appointments_select_own:SELECT:{authenticated} '
    || 'doctors:doctors_select_active:SELECT:{authenticated} '
    || 'patients:patients_insert_own:INSERT:{authenticated} '
    || 'patients:patients_select_own:SELECT:{authenticated} '
    || 'patients:patients_update_own:UPDATE:{authenticated} '
    || 'time_slots:time_slots_select_all:SELECT:{authenticated}',
  'policies are exactly the documented set (none on daily_token_counters)');

select harness.eq(
  (select string_agg(format('%s|%s|%s|%s', id, name, specialty, avg_consult_minutes), ' ; '
                     order by id)
   from public.doctors),
  'dr-desilva|Dr. Michael De Silva|Cardiologist|20 ; dr-fernando|Dr. James Fernando|Pediatrician|12 ; '
    || 'dr-perera|Dr. Sarah Perera|General Practitioner|10 ; dr-sharma|Dr. Anita Sharma|Dermatologist|15',
  'doctors seeded once (re-run did not duplicate)');

select harness.eq(
  (select string_agg(format('%s=%s', to_char('2000-01-01'::date + slot_time, 'HH24:MI'), label),
                     ' ' order by slot_time)
   from public.time_slots),
  '09:00=09:00 AM 09:30=09:30 AM 10:00=10:00 AM 10:30=10:30 AM 11:00=11:00 AM '
    || '14:00=02:00 PM 14:30=02:30 PM 15:00=03:00 PM 16:00=04:00 PM',
  'time slots seeded once with A2 labels');

-- ---------------------------------------------------------------------------------------------
\echo '== test fixtures (superuser)'
-- ---------------------------------------------------------------------------------------------

insert into auth.users (id, email) values
  (:'a', 'patient.a@example.com'),
  (:'b', 'patient.b@example.com'),
  (:'c', 'patient.c@example.com'),
  (:'d', 'no.details@example.com'),
  (:'e', 'patient.e@example.com'),
  (:'f', 'patient.f@example.com'),
  (:'g', 'patient.g@example.com'),
  (:'h', 'patient.h@example.com'),
  (:'i', 'patient.i@example.com'),
  (:'j', 'patient.j@example.com');

insert into public.patients (id, first_name, last_name, mobile, email)
select u.id, 'Patient', upper(right(u.id::text, 2)), '0400 000 100', u.email
from auth.users u
where u.id in (:'e', :'f', :'g', :'h', :'i', :'j');

insert into public.doctors (id, name, specialty, active)
values ('dr-inactive', 'Dr. Inactive Example', 'General Practitioner', false);

-- ---------------------------------------------------------------------------------------------
\echo '== anon can do nothing'
-- ---------------------------------------------------------------------------------------------

begin;
select harness.login(null);
set local role anon;
select harness.expect_error('select * from public.doctors', '42501', 'anon cannot read doctors');
select harness.expect_error('select * from public.time_slots', '42501', 'anon cannot read time_slots');
select harness.expect_error('select * from public.patients', '42501', 'anon cannot read patients');
select harness.expect_error('select * from public.appointments', '42501', 'anon cannot read appointments');
select harness.expect_error('select * from public.daily_token_counters', '42501',
  'anon cannot read daily_token_counters');
select harness.expect_error(
  $$insert into public.patients (id, first_name, last_name, mobile, email)
    values (gen_random_uuid(), 'X', 'Y', '0400 000 000', 'x@example.com')$$,
  '42501', 'anon cannot insert patients');
select harness.expect_error('select public.clinic_today()', '42501', 'anon cannot execute clinic_today');
select harness.expect_error('select public.clinic_now_time()', '42501', 'anon cannot execute clinic_now_time');
select harness.expect_error($$select * from public.available_slots('dr-perera', current_date + 1)$$,
  '42501', 'anon cannot execute available_slots');
select harness.expect_error($$select * from public.book_appointment('dr-perera', current_date + 1, '09:00')$$,
  '42501', 'anon cannot execute book_appointment');
select harness.expect_error('select * from public.current_appointment()', '42501',
  'anon cannot execute current_appointment');
select harness.expect_error('select * from public.queue_snapshot(gen_random_uuid())', '42501',
  'anon cannot execute queue_snapshot');
rollback;

-- ---------------------------------------------------------------------------------------------
\echo '== patients: own row only'
-- ---------------------------------------------------------------------------------------------

begin;
select harness.login(:'a');
set local role authenticated;
with i as (
  insert into public.patients (id, first_name, last_name, mobile, email)
  values (:'a', 'Alice', 'Example', '+61 400 000 001', 'patient.a@example.com')
  returning 1
)
select harness.eq(count(*)::int, 1, 'A can insert own patient row') from i;
select harness.expect_error(
  format($$insert into public.patients (id, first_name, last_name, mobile, email)
           values (%L, 'Dee', 'Example', '0400 000 004', 'd@example.com')$$, :'d'),
  '42501', 'A cannot insert a patient row for another user');
commit;

begin;
select harness.login(:'b');
set local role authenticated;
insert into public.patients (id, first_name, last_name, mobile, email)
values (:'b', 'Bob', 'Example', '(02) 9000 0002', 'patient.b@example.com');
commit;

begin;
select harness.login(:'c');
set local role authenticated;
insert into public.patients (id, first_name, last_name, mobile, email)
values (:'c', 'Cara', 'Example', '0400-000-003', 'patient.c@example.com');
commit;

select created_at as a_created_at, updated_at as a_updated_at
from public.patients where id = :'a' \gset

begin;
select harness.login(:'a');
set local role authenticated;
select harness.eq((select count(*)::int from public.patients), 1, 'A sees exactly one patient row');
select harness.eq((select id from public.patients), :'a'::uuid, 'the visible row is A own row');
select harness.eq((select count(*)::int from public.patients where id = :'b'), 0,
  'A cannot read the patient row of B');
with u as (update public.patients set first_name = 'Mallory' where id = :'b' returning 1)
select harness.eq(count(*)::int, 0, 'A cannot update the patient row of B') from u;
select harness.expect_error(format('update public.patients set id = %L where id = %L', :'d', :'a'),
  '42501', 'A cannot re-key own row to another user id');
select harness.expect_error('delete from public.patients', '42501', 'patients cannot delete rows');
select harness.expect_error(format($$update public.patients set mobile = 'call me' where id = %L$$, :'a'),
  '23514', 'invalid mobile rejected by check constraint');
select harness.expect_error(format($$update public.patients set email = 'no-at-sign' where id = %L$$, :'a'),
  '23514', 'email without @ rejected by check constraint');
select harness.expect_error(format($$update public.patients set first_name = '' where id = %L$$, :'a'),
  '23514', 'empty first name rejected by check constraint');
select harness.expect_error(format('update public.patients set last_name = repeat(%L, 81) where id = %L',
  'x', :'a'), '23514', '81-char last name rejected by check constraint');
select harness.expect_error('select public.set_patient_timestamps()', '42501',
  'authenticated cannot execute the trigger function');
with u as (
  update public.patients
  set first_name = 'Alicia', created_at = '2000-01-01', updated_at = '2000-01-01'
  where id = :'a'
  returning 1
)
select harness.eq(count(*)::int, 1, 'A can update own patient row') from u;
commit;

select harness.eq((select first_name from public.patients where id = :'b'), 'Bob',
  'patient B is unchanged');
select harness.eq((select created_at from public.patients where id = :'a'), :'a_created_at'::timestamptz,
  'created_at cannot be overwritten');
select harness.ok((select updated_at from public.patients where id = :'a') > :'a_updated_at'::timestamptz,
  'updated_at is refreshed by the trigger on update');

-- PostgREST upsert (the backend's upsert_patient) issues INSERT ... ON CONFLICT (id) DO UPDATE.
begin;
select harness.login(:'a');
set local role authenticated;
with u as (
  insert into public.patients as p (id, first_name, last_name, mobile, email)
  values (:'a', 'Alice', 'Example', '+61 400 000 001', 'patient.a@example.com')
  on conflict (id) do update set first_name = excluded.first_name, last_name = excluded.last_name,
    mobile = excluded.mobile, email = excluded.email
  returning p.first_name
)
select harness.eq((select first_name from u), 'Alice', 'upsert updates own existing row');
select harness.expect_error(
  format($$insert into public.patients (id, first_name, last_name, mobile, email)
           values (%L, 'Mallory', 'Example', '0400 000 009', 'm@example.com')
           on conflict (id) do update set first_name = excluded.first_name$$, :'b'),
  '42501', 'upsert cannot overwrite the existing row of B');
commit;

begin;
select harness.login(:'d');
set local role authenticated;
with u as (
  insert into public.patients (id, first_name, last_name, mobile, email)
  values (:'d', 'Dee', 'Example', '0400 000 004', 'no.details@example.com')
  on conflict (id) do update set first_name = excluded.first_name
  returning 1
)
select harness.eq(count(*)::int, 1, 'upsert inserts a missing own row') from u;
rollback;

select harness.eq((select first_name from public.patients where id = :'b'), 'Bob',
  'patient B is still unchanged after the upsert attempt');

-- ---------------------------------------------------------------------------------------------
\echo '== reference data for authenticated users'
-- ---------------------------------------------------------------------------------------------

begin;
select harness.login(:'a');
set local role authenticated;
select harness.eq((select string_agg(id, ' ' order by id) from public.doctors),
  'dr-desilva dr-fernando dr-perera dr-sharma', 'authenticated sees only active doctors');
select harness.eq((select count(*)::int from public.time_slots), 9, 'authenticated sees all time slots');
select harness.eq(public.clinic_today(), (now() at time zone 'Australia/Sydney')::date,
  'authenticated can execute clinic_today (the Sydney date)');
select harness.expect_error($$insert into public.doctors (id, name, specialty) values ('dr-x', 'X', 'Y')$$,
  '42501', 'authenticated cannot write doctors');
select harness.expect_error($$delete from public.time_slots$$, '42501', 'authenticated cannot write time_slots');
rollback;

-- ---------------------------------------------------------------------------------------------
\echo '== book_appointment: error codes'
-- ---------------------------------------------------------------------------------------------

begin;
select harness.login(null);
set local role authenticated;
select harness.expect_error($$select public.book_appointment('dr-perera', public.clinic_today() + 1, '09:00')$$,
  'PC401', 'booking without a user -> PC401');
select harness.expect_error($$select * from public.available_slots('dr-perera', public.clinic_today() + 1)$$,
  'PC401', 'available_slots without a user -> PC401');
select harness.expect_error('select * from public.queue_snapshot(gen_random_uuid())',
  'PC401', 'queue_snapshot without a user -> PC401');
select harness.eq((select count(*)::int from public.current_appointment()), 0,
  'current_appointment without a user returns no rows');
rollback;

begin;
select harness.login(:'d');
set local role authenticated;
select harness.expect_error($$select public.book_appointment('dr-perera', public.clinic_today() + 1, '09:00')$$,
  'PC412', 'booking without patient details -> PC412', 'Please complete your patient details first.');
select harness.expect_error($$select public.book_appointment('dr-nobody', public.clinic_today() - 1, '09:15')$$,
  'PC412', 'PC412 is checked before input validation');
select harness.eq((select count(*)::int from public.current_appointment()), 0,
  'user without bookings has no current appointment');
rollback;

begin;
select harness.login(:'a');
set local role authenticated;
select harness.expect_error($$select public.book_appointment('dr-perera', public.clinic_today() - 1, '09:00')$$,
  'PC400', 'past date -> PC400', 'Please choose today or a future date.');
select harness.expect_error($$select public.book_appointment('dr-perera', null, '09:00')$$,
  'PC400', 'missing date -> PC400', 'Please choose today or a future date.');
select harness.expect_error($$select public.book_appointment('dr-perera', public.clinic_today() + 91, '09:00')$$,
  'PC400', 'more than 90 days ahead -> PC400', 'Appointments can only be booked up to 90 days ahead.');
select harness.expect_error($$select public.book_appointment('dr-nobody', public.clinic_today() + 1, '09:00')$$,
  'PC400', 'unknown doctor -> PC400', 'Please choose a valid doctor.');
select harness.expect_error($$select public.book_appointment('dr-inactive', public.clinic_today() + 1, '09:00')$$,
  'PC400', 'inactive doctor -> PC400', 'Please choose a valid doctor.');
select harness.expect_error($$select public.book_appointment('dr-perera', public.clinic_today() + 1, '09:15')$$,
  'PC400', 'unknown slot -> PC400', 'Please choose a valid time slot.');
select harness.expect_error(
  format($$insert into public.appointments (patient_id, doctor_id, appointment_date, slot_time, token_number)
           values (%L, 'dr-perera', public.clinic_today() + 1, '09:00', 1)$$, :'a'),
  '42501', 'direct INSERT into appointments is denied');
select harness.expect_error($$update public.appointments set status = 'completed'$$, '42501',
  'direct UPDATE of appointments is denied');
select harness.expect_error('delete from public.appointments', '42501',
  'direct DELETE of appointments is denied');
select harness.expect_error('select * from public.daily_token_counters', '42501',
  'authenticated cannot read daily_token_counters');
select harness.expect_error('update public.daily_token_counters set last_number = 0', '42501',
  'authenticated cannot write daily_token_counters');
rollback;

select harness.eq((select count(*)::int from public.daily_token_counters), 0,
  'rejected bookings did not consume tokens');

-- ---------------------------------------------------------------------------------------------
\echo '== book_appointment: sequential tokens per date, double booking'
-- ---------------------------------------------------------------------------------------------

-- Booked out of slot order on purpose: the queue must order by slot, not by token.
begin;
select harness.login(:'c');
set local role authenticated;
select * from public.book_appointment('dr-perera', public.clinic_today() + 1, '10:00') \gset c_
commit;

begin;
select harness.login(:'a');
set local role authenticated;
select * from public.book_appointment('dr-perera', public.clinic_today() + 1, '09:00') \gset a_
commit;

begin;
select harness.login(:'b');
set local role authenticated;
select * from public.book_appointment('dr-perera', public.clinic_today() + 1, '09:30') \gset b_
commit;

select harness.eq(:'c_token'::text, 'PC-001', 'first booking of a date gets PC-001');
select harness.eq(:'a_token'::text, 'PC-002', 'second booking gets PC-002');
select harness.eq(:'b_token'::text, 'PC-003', 'third booking gets PC-003');
select harness.eq(format('%s|%s|%s', :'a_patient_id', :'a_status', :'a_token_number'),
  format('%s|waiting|2', :'a'), 'booking returns the inserted row (own patient, waiting)');

begin;
select harness.login(:'e');
set local role authenticated;
select harness.expect_error($$select public.book_appointment('dr-perera', public.clinic_today() + 1, '09:00')$$,
  'PC409', 'double booking a taken slot -> PC409', 'That time slot has just been booked. Please choose another.');
select * from public.book_appointment('dr-sharma', public.clinic_today() + 1, '09:00') \gset e_
commit;

select harness.eq(:'e_token'::text, 'PC-004',
  'counter is per date across doctors and a rejected booking leaves no gap');

begin;
select harness.login(:'f');
set local role authenticated;
select * from public.book_appointment('dr-fernando', public.clinic_today() + 2, '09:00') \gset f_
commit;

select harness.eq(:'f_token'::text, 'PC-001', 'a different date starts again at PC-001');

-- ---------------------------------------------------------------------------------------------
\echo '== available_slots'
-- ---------------------------------------------------------------------------------------------

begin;
select harness.login(:'a');
set local role authenticated;
select harness.eq(
  (select string_agg(label, ',' order by slot_time)
   from public.available_slots('dr-perera', public.clinic_today() + 1)),
  '10:30 AM,11:00 AM,02:00 PM,02:30 PM,03:00 PM,04:00 PM',
  'taken slots are hidden and results are ordered by time');
select harness.eq((select count(*)::int from public.available_slots('dr-desilva', public.clinic_today() + 1)),
  9, 'another doctor on the same date has every slot free');
select harness.eq((select count(*)::int from public.available_slots('dr-desilva', public.clinic_today() + 90)),
  9, '90 days ahead is bookable');
select harness.eq((select count(*)::int from public.available_slots('dr-desilva', public.clinic_today() + 91)),
  0, 'more than 90 days ahead returns nothing');
select harness.eq((select count(*)::int from public.available_slots('dr-desilva', public.clinic_today() - 1)),
  0, 'past date returns nothing');
select harness.eq((select count(*)::int from public.available_slots('dr-desilva', null)),
  0, 'missing date returns nothing');
select harness.eq((select count(*)::int from public.available_slots('dr-nobody', public.clinic_today() + 1)),
  0, 'unknown doctor returns nothing');
select harness.eq((select count(*)::int from public.available_slots('dr-inactive', public.clinic_today() + 1)),
  0, 'inactive doctor returns nothing');
select harness.eq(
  (select array_agg(s.slot_time order by s.slot_time)
   from public.available_slots('dr-desilva', public.clinic_today()) s),
  (select array_agg(ts.slot_time order by ts.slot_time)
   from public.time_slots ts where ts.slot_time > public.clinic_now_time()),
  'today (real Sydney clock) lists only slots later than the clinic clock');
rollback;

-- ---------------------------------------------------------------------------------------------
\echo '== book_appointment: one active upcoming appointment per patient'
-- ---------------------------------------------------------------------------------------------

-- A holds PC-002 (waiting, tomorrow).
begin;
select harness.login(:'a');
set local role authenticated;
select harness.expect_error($$select public.book_appointment('dr-desilva', public.clinic_today() + 5, '10:00')$$,
  'PC400', 'a second active booking on another date -> PC400', :'already_booked');
select harness.expect_error($$select public.book_appointment('dr-perera', public.clinic_today() + 1, '10:30')$$,
  'PC400', 'a second active booking on the same date -> PC400', :'already_booked');
select harness.expect_error($$select public.book_appointment('dr-nobody', public.clinic_today() + 1, '09:15')$$,
  'PC400', 'the upcoming-appointment check runs right after PC412', :'already_booked');
rollback;

begin;
update public.appointments set status = 'in_consultation' where id = :'a_id';
select harness.login(:'a');
set local role authenticated;
select harness.expect_error($$select public.book_appointment('dr-desilva', public.clinic_today() + 5, '10:00')$$,
  'PC400', 'an in-consultation upcoming appointment also blocks -> PC400', :'already_booked');
rollback;

begin;
update public.appointments set status = 'completed' where id = :'a_id';
select harness.login(:'a');
set local role authenticated;
select harness.eq(
  (select n.status from public.book_appointment('dr-desilva', public.clinic_today() + 5, '10:00') n),
  'waiting', 'a completed upcoming appointment does not block a new booking');
rollback;

begin;
update public.appointments set status = 'cancelled' where id = :'a_id';
select harness.login(:'a');
set local role authenticated;
select harness.eq(
  (select n.status from public.book_appointment('dr-desilva', public.clinic_today() + 5, '10:00') n),
  'waiting', 'a cancelled upcoming appointment does not block a new booking');
rollback;

-- Inserted directly (the RPC refuses past dates): G's only active rows are before clinic today.
insert into public.appointments (patient_id, doctor_id, appointment_date, slot_time, token_number, status)
values (:'g', 'dr-desilva', public.clinic_today() - 1, '09:00', 1, 'waiting'),
       (:'g', 'dr-desilva', public.clinic_today() - 7, '09:00', 1, 'in_consultation');

begin;
select harness.login(:'g');
set local role authenticated;
select * from public.book_appointment('dr-sharma', public.clinic_today() + 8, '09:00') \gset g_
commit;

select harness.eq(format('%s|%s', :'g_token', :'g_status'), 'PC-001|waiting',
  'past-dated waiting and in-consultation appointments do not block a new booking');

-- ---------------------------------------------------------------------------------------------
\echo '== appointments RLS and current_appointment'
-- ---------------------------------------------------------------------------------------------

begin;
select harness.login(:'a');
set local role authenticated;
select harness.eq((select count(*)::int from public.appointments), 1, 'A sees exactly own one appointment');
select harness.eq((select count(*)::int from public.appointments where patient_id <> :'a'), 0,
  'A cannot see appointments of other patients');
select harness.eq((select count(*)::int from public.appointments where id = :'b_id'), 0,
  'A cannot read the appointment of B by id');
select harness.eq(
  (select format('%s|%s|%s|%s|%s|%s|%s', token, appointment_date - public.clinic_today(), slot_label,
                 status, doctor_id, doctor_name, doctor_specialty)
   from public.current_appointment()),
  'PC-002|1|09:00 AM|waiting|dr-perera|Dr. Sarah Perera|General Practitioner',
  'current_appointment returns the upcoming booking of A');
select harness.eq((select count(*)::int from public.current_appointment()), 1,
  'current_appointment returns at most one row');
rollback;

begin;
select harness.login(:'e');
set local role authenticated;
select harness.eq((select string_agg(token, ' ' order by token) from public.appointments), 'PC-004',
  'E sees only own appointments');
select harness.eq((select id from public.current_appointment()), :'e_id'::uuid,
  'current_appointment for E is the booking of E');
rollback;

begin;
select harness.login(:'g');
set local role authenticated;
select harness.eq((select string_agg(token, ' ' order by appointment_date) from public.appointments),
  'PC-001 PC-001 PC-001', 'G sees all three own appointments');
select harness.eq((select id from public.current_appointment()), :'g_id'::uuid,
  'current_appointment for G skips the past-dated active appointments');
rollback;

-- Inserted directly and created after PC-002: completed, cancelled and past rows are never
-- "current", even when they are newer.
begin;
insert into public.appointments (patient_id, doctor_id, appointment_date, slot_time, token_number, status)
values (:'a', 'dr-fernando', public.clinic_today() + 2, '10:00', 901, 'completed'),
       (:'a', 'dr-fernando', public.clinic_today() + 2, '10:30', 902, 'cancelled'),
       (:'a', 'dr-sharma', public.clinic_today() - 1, '09:00', 903, 'waiting');
select harness.login(:'a');
set local role authenticated;
select harness.eq((select id from public.current_appointment()), :'a_id'::uuid,
  'current_appointment skips newer completed, cancelled and past appointments');
rollback;

-- Rows from before the one-upcoming-appointment rule: the newest active upcoming one wins.
begin;
insert into public.appointments (patient_id, doctor_id, appointment_date, slot_time, token_number, created_at)
values (:'a', 'dr-sharma', public.clinic_today() + 9, '09:00', 1, now() + interval '1 minute')
returning id as legacy_id \gset
select harness.login(:'a');
set local role authenticated;
select harness.eq((select id from public.current_appointment()), :'legacy_id'::uuid,
  'with two active upcoming rows, current_appointment returns the most recently created');
rollback;

-- ---------------------------------------------------------------------------------------------
\echo '== queue_snapshot (dr-perera tomorrow: A 09:00 PC-002, B 09:30 PC-003, C 10:00 PC-001)'
-- ---------------------------------------------------------------------------------------------

begin;
select harness.login(:'a');
set local role authenticated;
select harness.eq(
  (select format('%s|%s|%s|%s|%s|%s|%s', token, queue_position, total_in_queue, now_serving_token,
                 avg_consult_minutes, is_today, status)
   from public.queue_snapshot(:'a_id')),
  'PC-002|1|3|PC-002|10|f|waiting', 'A is first of three and is now serving');
select harness.eq((select count(*)::int from public.queue_snapshot(:'a_id')), 1,
  'queue_snapshot returns exactly one row');
select harness.expect_error(format('select * from public.queue_snapshot(%L)', :'b_id'), 'PC404',
  'A cannot snapshot the appointment of B -> PC404');
select harness.expect_error('select * from public.queue_snapshot(gen_random_uuid())', 'PC404',
  'unknown appointment id -> PC404');
rollback;

begin;
select harness.login(:'b');
set local role authenticated;
select harness.eq(
  (select format('%s|%s|%s|%s', token, queue_position, total_in_queue, now_serving_token)
   from public.queue_snapshot(:'b_id')),
  'PC-003|2|3|PC-002', 'B is second of three');
rollback;

begin;
select harness.login(:'c');
set local role authenticated;
select harness.eq(
  (select format('%s|%s|%s|%s', token, queue_position, total_in_queue, now_serving_token)
   from public.queue_snapshot(:'c_id')),
  'PC-001|3|3|PC-002', 'C is third of three despite holding the lowest token');
rollback;

update public.appointments set status = 'in_consultation' where id = :'a_id';

begin;
select harness.login(:'b');
set local role authenticated;
select harness.eq(
  (select format('%s|%s|%s', queue_position, total_in_queue, now_serving_token)
   from public.queue_snapshot(:'b_id')),
  '2|3|PC-002', 'an in-consultation appointment stays in the queue');
rollback;

update public.appointments set status = 'completed' where id = :'a_id';

begin;
select harness.login(:'b');
set local role authenticated;
select harness.eq(
  (select format('%s|%s|%s', queue_position, total_in_queue, now_serving_token)
   from public.queue_snapshot(:'b_id')),
  '1|2|PC-003', 'after A completes, B is first of two and now serving');
select harness.login(:'a');
select harness.eq(
  (select format('%s|%s|%s|%s', coalesce(queue_position::text, 'null'), total_in_queue,
                 now_serving_token, status)
   from public.queue_snapshot(:'a_id')),
  'null|2|PC-003|completed', 'a completed appointment has no queue position');
rollback;

-- ---------------------------------------------------------------------------------------------
\echo '== cancelled slots can be rebooked'
-- ---------------------------------------------------------------------------------------------

-- C cancels; A (whose PC-002 is now completed) books the freed slot.
update public.appointments set status = 'cancelled' where id = :'c_id';

begin;
select harness.login(:'a');
set local role authenticated;
select harness.ok(
  exists (select 1 from public.available_slots('dr-perera', public.clinic_today() + 1) s
          where s.slot_time = '10:00'),
  'a cancelled slot is offered again');
select * from public.book_appointment('dr-perera', public.clinic_today() + 1, '10:00') \gset a3_
commit;

select harness.eq(:'a3_token'::text, 'PC-005', 'rebooking a cancelled slot succeeds with the next token');

-- ---------------------------------------------------------------------------------------------
\echo '== token formatting'
-- ---------------------------------------------------------------------------------------------

insert into public.daily_token_counters (token_date, last_number)
values (public.clinic_today() + 3, 999)
on conflict (token_date) do update set last_number = excluded.last_number;

-- C's only appointment is cancelled, so C can book again.
begin;
select harness.login(:'c');
set local role authenticated;
select * from public.book_appointment('dr-desilva', public.clinic_today() + 3, '09:00') \gset t1_
commit;

begin;
select harness.login(:'h');
set local role authenticated;
select * from public.book_appointment('dr-desilva', public.clinic_today() + 3, '09:30') \gset t2_
commit;

select harness.eq(format('%s %s', :'t1_token', :'t2_token'), 'PC-1000 PC-1001',
  'tokens from 1000 upwards are not truncated');

begin;
insert into public.appointments (patient_id, doctor_id, appointment_date, slot_time, token_number)
select :'c', 'dr-perera', public.clinic_today() + 4, ts.slot_time, n.n
from unnest(array[1, 42, 999, 1000, 123456]) with ordinality as n(n, i)
join (select slot_time, row_number() over (order by slot_time) as i from public.time_slots) ts using (i);
select harness.eq(
  (select string_agg(token, ' ' order by token_number) from public.appointments
   where appointment_date = public.clinic_today() + 4),
  'PC-001 PC-042 PC-999 PC-1000 PC-123456', 'generated token column pads only below 1000');
rollback;

-- ---------------------------------------------------------------------------------------------
\echo '== today (clinic clock pinned to 14:00 inside a rolled-back transaction)'
-- ---------------------------------------------------------------------------------------------

-- DDL is transactional and the RPCs call public.clinic_now_time() fully qualified, so pinning
-- it here makes the "today" rules deterministic; rollback restores the real function.
begin;
create or replace function public.clinic_now_time()
returns time
language sql
stable
set search_path = ''
as $$
  select time '14:00';
$$;
select harness.login(:'i');
set local role authenticated;
select harness.eq(
  (select string_agg(label, ',' order by slot_time)
   from public.available_slots('dr-sharma', public.clinic_today())),
  '02:30 PM,03:00 PM,04:00 PM', 'today lists only slots after the pinned clock');
select harness.expect_error($$select public.book_appointment('dr-sharma', public.clinic_today(), '11:00')$$,
  'PC400', 'a slot earlier today -> PC400', 'That time slot has already passed. Please choose a later time.');
select harness.expect_error($$select public.book_appointment('dr-sharma', public.clinic_today(), '14:00')$$,
  'PC400', 'the slot at exactly the current time -> PC400',
  'That time slot has already passed. Please choose a later time.');
select * from public.book_appointment('dr-sharma', public.clinic_today(), '14:30') \gset today_
select harness.eq(:'today_token'::text, 'PC-001', 'a later slot today can be booked');
select harness.eq((select is_today from public.queue_snapshot(:'today_id')), true,
  'is_today is true for a booking dated clinic today');
select harness.eq((select id from public.current_appointment()), :'today_id'::uuid,
  'a booking for later today is the current appointment');
rollback;

select harness.eq(
  (select prosrc from pg_proc where oid = 'public.clinic_now_time()'::regprocedure) like '%Australia/Sydney%',
  true, 'the real clinic_now_time is restored after the pinned-clock checks');

-- ---------------------------------------------------------------------------------------------
\echo '== concurrent double submit by one patient (second psql session)'
-- ---------------------------------------------------------------------------------------------

-- This session books for J and keeps the transaction open. Meanwhile a second session
-- (concurrent_peer.sql) books for J on another date, so the two bookings share no counter row.
-- The second booking must wait for the first one, then be refused.
\if :{?peer_ready}
insert into harness.peer (sub, sql)
values (:'j', $$select public.book_appointment('dr-perera', public.clinic_today() + 7, '09:00')$$);

begin;
select harness.login(:'j');
set local role authenticated;
select * from public.book_appointment('dr-perera', public.clinic_today() + 6, '09:00') \gset conc_
reset role;
\! "$PC_HARNESS_PSQL" -X -q -v ON_ERROR_STOP=1 -v db="$PC_HARNESS_DB" -f "$PC_HARNESS_PEER_SQL" "$PC_HARNESS_URL" >"$PC_HARNESS_PEER_LOG" 2>&1 &
select harness.eq(harness.wait_for_peer(), 'blocked',
  'a concurrent booking by the same patient waits for the first one to commit');
commit;

select harness.eq(harness.peer_result(), 'PC400: ' || :'already_booked',
  'once the first booking commits, the concurrent one is refused with PC400');
select harness.eq(
  (select string_agg(format('%s|%s', appointment_date - public.clinic_today(), token), ' ')
   from public.appointments where patient_id = :'j'),
  '6|PC-001', 'concurrent double submit for two dates yields exactly one booking');
\else
select harness.skip('concurrent double submit (start the checks with run_checks.sh)');
\endif

-- ---------------------------------------------------------------------------------------------
\echo '== deleting an auth user cascades'
-- ---------------------------------------------------------------------------------------------

delete from auth.users where id = :'b';
select harness.eq(
  (select count(*)::int from public.patients where id = :'b')
    + (select count(*)::int from public.appointments where patient_id = :'b'),
  0, 'patient row and appointments of a deleted user are removed');

\o
\echo 'ALL CHECKS PASSED'
