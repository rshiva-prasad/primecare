-- LOCAL TEST ONLY. Minimal stand-in for the parts of Supabase that 0001_init.sql relies on:
-- the anon/authenticated/service_role roles, auth.users, auth.uid() and Supabase's default
-- privileges on the public schema (so the migration's revokes are genuinely exercised).
-- Never run this against a real Supabase project.

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'supabase_admin') then
    raise exception 'auth_stub.sql must not be run against a real Supabase database';
  end if;
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end;
$$;

create schema if not exists auth;
grant usage on schema auth to anon, authenticated, service_role;

create table if not exists auth.users (
  id uuid primary key,
  email text
);

-- Same resolution order as Supabase: JWT claims JSON first, then the legacy single-claim GUC.
-- nullif guards against '' (what current_setting returns once a GUC has been reset).
create or replace function auth.uid()
returns uuid
language sql
stable
as $$
  select coalesce(
    nullif(nullif(current_setting('request.jwt.claims', true), '')::json ->> 'sub', ''),
    nullif(current_setting('request.jwt.claim.sub', true), '')
  )::uuid;
$$;

grant execute on function auth.uid() to anon, authenticated, service_role;

grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
