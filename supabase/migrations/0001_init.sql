-- PrimeCare Clinic (BUS4012 A3) - initial schema: tables, RLS, grants, RPC functions, seed data.
--
-- How to run: Supabase Dashboard -> SQL Editor -> New query -> paste this whole file -> Run.
-- The script is transactional and safe to re-run (if not exists / create or replace /
-- drop policy if exists / on conflict do nothing). It never modifies the auth schema.
--
-- Clinic time zone is Australia/Sydney; "today" is decided only by public.clinic_today().
-- Custom SQLSTATEs (mapped by the backend): PC400 invalid input, PC401 not authenticated,
-- PC404 not found, PC409 slot already booked, PC412 patient details required.
-- Least privilege: Supabase auto-grants anon/authenticated/service_role on new public tables
-- and functions, so every grant is revoked below and only what the app needs is re-granted.

begin;

-- ---------------------------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------------------------

create table if not exists public.doctors (
  id text primary key,
  name text not null,
  specialty text not null,
  avg_consult_minutes int not null default 10 check (avg_consult_minutes between 1 and 120),
  active boolean not null default true
);

create table if not exists public.time_slots (
  slot_time time primary key,
  label text not null
);

create table if not exists public.patients (
  id uuid primary key references auth.users (id) on delete cascade,
  first_name text not null check (char_length(first_name) between 1 and 80),
  last_name text not null check (char_length(last_name) between 1 and 80),
  mobile text not null check (mobile ~ '^\+?[0-9 ()-]{7,20}$'),
  email text not null check (char_length(email) <= 254 and strpos(email, '@') > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.appointments (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.patients (id) on delete cascade,
  doctor_id text not null references public.doctors (id),
  appointment_date date not null,
  slot_time time not null references public.time_slots (slot_time),
  token_number int not null check (token_number > 0),
  -- lpad would truncate 1000+ to 3 chars, so only pad below 1000.
  token text generated always as (
    'PC-' || case when token_number < 1000 then lpad(token_number::text, 3, '0')
                  else token_number::text end
  ) stored,
  status text not null default 'waiting'
    check (status in ('waiting', 'in_consultation', 'completed', 'cancelled')),
  created_at timestamptz not null default now(),
  unique (appointment_date, token_number)
);

-- Only reachable through public.book_appointment (no grants, no policies).
create table if not exists public.daily_token_counters (
  token_date date primary key,
  last_number int not null default 0
);

create unique index if not exists appointments_active_slot_key
  on public.appointments (doctor_id, appointment_date, slot_time)
  where status <> 'cancelled';
create index if not exists appointments_patient_created_idx
  on public.appointments (patient_id, created_at desc);
create index if not exists appointments_queue_idx
  on public.appointments (doctor_id, appointment_date, slot_time);

-- Server-maintained timestamps: created_at cannot be forged, updated_at always current.
create or replace function public.set_patient_timestamps()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    new.created_at := now();
  else
    new.created_at := old.created_at;
  end if;
  new.updated_at := now();
  return new;
end;
$$;

create or replace trigger patients_set_timestamps
  before insert or update on public.patients
  for each row execute function public.set_patient_timestamps();

-- ---------------------------------------------------------------------------------------------
-- Row level security and table privileges
-- ---------------------------------------------------------------------------------------------

alter table public.doctors enable row level security;
alter table public.time_slots enable row level security;
alter table public.patients enable row level security;
alter table public.appointments enable row level security;
alter table public.daily_token_counters enable row level security;

revoke all on table
  public.doctors, public.time_slots, public.patients, public.appointments,
  public.daily_token_counters
  from public, anon, authenticated, service_role;

grant select on table public.doctors, public.time_slots to authenticated;
grant select, insert, update on table public.patients to authenticated;
grant select on table public.appointments to authenticated;

drop policy if exists doctors_select_active on public.doctors;
create policy doctors_select_active on public.doctors
  for select to authenticated
  using (active);

drop policy if exists time_slots_select_all on public.time_slots;
create policy time_slots_select_all on public.time_slots
  for select to authenticated
  using (true);

drop policy if exists patients_select_own on public.patients;
create policy patients_select_own on public.patients
  for select to authenticated
  using (id = (select auth.uid()));

drop policy if exists patients_insert_own on public.patients;
create policy patients_insert_own on public.patients
  for insert to authenticated
  with check (id = (select auth.uid()));

drop policy if exists patients_update_own on public.patients;
create policy patients_update_own on public.patients
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

drop policy if exists appointments_select_own on public.appointments;
create policy appointments_select_own on public.appointments
  for select to authenticated
  using (patient_id = (select auth.uid()));

-- ---------------------------------------------------------------------------------------------
-- Functions (RPC)
-- ---------------------------------------------------------------------------------------------

create or replace function public.clinic_today()
returns date
language sql
stable
set search_path = ''
as $$
  select (now() at time zone 'Australia/Sydney')::date;
$$;

create or replace function public.clinic_now_time()
returns time
language sql
stable
set search_path = ''
as $$
  select (now() at time zone 'Australia/Sydney')::time;
$$;

-- Free slots for a doctor and date. Reveals no patient data.
create or replace function public.available_slots(p_doctor_id text, p_date date)
returns table (slot_time time, label text)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_today date := public.clinic_today();
begin
  if auth.uid() is null then
    raise exception using errcode = 'PC401', message = 'Please log in to continue.';
  end if;

  if p_date is null or p_date < v_today or p_date > v_today + 90 then
    return;
  end if;

  -- Every column is alias-qualified: slot_time/label are also OUT parameters.
  return query
    select ts.slot_time, ts.label
    from public.time_slots ts
    where exists (
        select 1 from public.doctors d where d.id = p_doctor_id and d.active
      )
      and (p_date > v_today or ts.slot_time > public.clinic_now_time())
      and not exists (
        select 1
        from public.appointments a
        where a.doctor_id = p_doctor_id
          and a.appointment_date = p_date
          and a.slot_time = ts.slot_time
          and a.status <> 'cancelled'
      )
    order by ts.slot_time;
end;
$$;

create or replace function public.book_appointment(
  p_doctor_id text,
  p_date date,
  p_slot_time time
)
returns public.appointments
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_today date := public.clinic_today();
  v_token_number int;
  v_constraint text;
  v_row public.appointments;
begin
  if v_uid is null then
    raise exception using errcode = 'PC401', message = 'Please log in to continue.';
  end if;

  -- Locking the caller's patients row makes concurrent bookings by the same patient run one at a
  -- time (bookings for different dates do not share a counter row), so the check below sees them.
  perform 1 from public.patients p where p.id = v_uid for update;
  if not found then
    raise exception using errcode = 'PC412',
      message = 'Please complete your patient details first.';
  end if;

  -- One active upcoming appointment per patient; past-dated ones never block.
  if exists (
    select 1
    from public.appointments a
    where a.patient_id = v_uid
      and a.status in ('waiting', 'in_consultation')
      and a.appointment_date >= v_today
  ) then
    raise exception using errcode = 'PC400',
      message = 'You already have an upcoming appointment.';
  end if;

  if not exists (select 1 from public.doctors d where d.id = p_doctor_id and d.active) then
    raise exception using errcode = 'PC400', message = 'Please choose a valid doctor.';
  end if;

  if not exists (select 1 from public.time_slots ts where ts.slot_time = p_slot_time) then
    raise exception using errcode = 'PC400', message = 'Please choose a valid time slot.';
  end if;

  if p_date is null or p_date < v_today then
    raise exception using errcode = 'PC400',
      message = 'Please choose today or a future date.';
  end if;

  if p_date > v_today + 90 then
    raise exception using errcode = 'PC400',
      message = 'Appointments can only be booked up to 90 days ahead.';
  end if;

  if p_date = v_today and p_slot_time <= public.clinic_now_time() then
    raise exception using errcode = 'PC400',
      message = 'That time slot has already passed. Please choose a later time.';
  end if;

  -- The counter row lock serialises concurrent bookings for the same date.
  insert into public.daily_token_counters as c (token_date, last_number)
  values (p_date, 1)
  on conflict (token_date) do update set last_number = c.last_number + 1
  returning c.last_number into v_token_number;

  begin
    insert into public.appointments as a
      (patient_id, doctor_id, appointment_date, slot_time, token_number, status)
    values (v_uid, p_doctor_id, p_date, p_slot_time, v_token_number, 'waiting')
    returning a.* into v_row;
  exception
    when unique_violation then
      get stacked diagnostics v_constraint = constraint_name;
      if v_constraint = 'appointments_active_slot_key' then
        raise exception using errcode = 'PC409',
          message = 'That time slot has just been booked. Please choose another.';
      end if;
      raise;
  end;

  return v_row;
end;
$$;

-- SECURITY INVOKER: RLS limits this to the caller's own rows (the filter is defence in depth).
create or replace function public.current_appointment()
returns table (
  id uuid,
  token text,
  token_number int,
  appointment_date date,
  slot_time time,
  slot_label text,
  status text,
  doctor_id text,
  doctor_name text,
  doctor_specialty text,
  created_at timestamptz
)
language sql
stable
security invoker
set search_path = ''
as $$
  select a.id, a.token, a.token_number, a.appointment_date, a.slot_time, ts.label,
         a.status, a.doctor_id, d.name, d.specialty, a.created_at
  from public.appointments a
  join public.time_slots ts on ts.slot_time = a.slot_time
  join public.doctors d on d.id = a.doctor_id
  where a.patient_id = (select auth.uid())
    and a.status in ('waiting', 'in_consultation')
    and a.appointment_date >= public.clinic_today()
  order by a.created_at desc
  limit 1;
$$;

-- Queue position for one of the caller's appointments. Reveals only tokens and counts.
create or replace function public.queue_snapshot(p_appointment_id uuid)
returns table (
  token text,
  queue_position int,
  total_in_queue int,
  now_serving_token text,
  avg_consult_minutes int,
  is_today boolean,
  status text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_appt public.appointments;
begin
  if v_uid is null then
    raise exception using errcode = 'PC401', message = 'Please log in to continue.';
  end if;

  select a.* into v_appt
  from public.appointments a
  where a.id = p_appointment_id and a.patient_id = v_uid;

  if not found then
    raise exception using errcode = 'PC404', message = 'Appointment not found.';
  end if;

  -- Every column is alias-qualified: token/status/... are also OUT parameters.
  return query
    with q as (
      select a.id, a.token,
             row_number() over (order by a.slot_time, a.token_number)::int as pos
      from public.appointments a
      where a.doctor_id = v_appt.doctor_id
        and a.appointment_date = v_appt.appointment_date
        and a.status in ('waiting', 'in_consultation')
    )
    select v_appt.token,
           (select q.pos from q where q.id = v_appt.id),
           (select count(*)::int from q),
           (select q.token from q order by q.pos limit 1),
           (select d.avg_consult_minutes from public.doctors d where d.id = v_appt.doctor_id),
           v_appt.appointment_date = public.clinic_today(),
           v_appt.status;
end;
$$;

-- ---------------------------------------------------------------------------------------------
-- Function privileges
-- ---------------------------------------------------------------------------------------------

revoke all on function
  public.set_patient_timestamps(),
  public.clinic_today(),
  public.clinic_now_time(),
  public.available_slots(text, date),
  public.book_appointment(text, date, time),
  public.current_appointment(),
  public.queue_snapshot(uuid)
  from public, anon, authenticated, service_role;

grant execute on function
  public.clinic_today(),
  public.clinic_now_time(),
  public.available_slots(text, date),
  public.book_appointment(text, date, time),
  public.current_appointment(),
  public.queue_snapshot(uuid)
  to authenticated;

-- ---------------------------------------------------------------------------------------------
-- Seed data (idempotent)
-- ---------------------------------------------------------------------------------------------

insert into public.doctors (id, name, specialty, avg_consult_minutes) values
  ('dr-perera', 'Dr. Sarah Perera', 'General Practitioner', 10),
  ('dr-fernando', 'Dr. James Fernando', 'Pediatrician', 12),
  ('dr-sharma', 'Dr. Anita Sharma', 'Dermatologist', 15),
  ('dr-desilva', 'Dr. Michael De Silva', 'Cardiologist', 20)
on conflict (id) do nothing;

insert into public.time_slots (slot_time, label) values
  ('09:00', '09:00 AM'),
  ('09:30', '09:30 AM'),
  ('10:00', '10:00 AM'),
  ('10:30', '10:30 AM'),
  ('11:00', '11:00 AM'),
  ('14:00', '02:00 PM'),
  ('14:30', '02:30 PM'),
  ('15:00', '03:00 PM'),
  ('16:00', '04:00 PM')
on conflict (slot_time) do nothing;

-- Ask PostgREST to pick up the new tables/functions immediately (no-op without PostgREST).
notify pgrst, 'reload schema';

commit;
