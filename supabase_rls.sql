-- Row Level Security (RLS) setup for the CSAFE AI Image Alteration Tracker.
--
-- The app talks to Supabase with the shared publishable "anon" key and has no
-- per-user login, so these policies grant the anon role exactly the four
-- operations the app performs on the `records` table:
--   * select  -> load records
--   * insert  -> save a new record (upsert)
--   * update  -> save an existing record (upsert)
--   * delete  -> delete button
--
-- This is the recommended baseline: it clears Supabase's "Unrestricted" warning,
-- default-denies every other table, and enforces least privilege. It does NOT
-- protect data from someone who already holds the anon key — that requires
-- per-user authentication (Supabase Auth), tracked separately as a future
-- feature.
--
-- How to run: Supabase dashboard -> SQL Editor -> New query -> paste -> Run.
-- Re-running is safe: each policy is dropped first so the script is idempotent.

-- Enable Row Level Security on the records table.
alter table public.records enable row level security;

-- App reads all records (load).
drop policy if exists "anon read records" on public.records;
create policy "anon read records"
  on public.records for select
  to anon using (true);

-- App creates records (save -> insert).
drop policy if exists "anon insert records" on public.records;
create policy "anon insert records"
  on public.records for insert
  to anon with check (true);

-- App updates records (save -> upsert).
drop policy if exists "anon update records" on public.records;
create policy "anon update records"
  on public.records for update
  to anon using (true) with check (true);

-- App deletes records (delete button).
-- To prevent students from deleting records, omit this policy (and hide the
-- Delete button in the app); deletes would then require the service-role key.
drop policy if exists "anon delete records" on public.records;
create policy "anon delete records"
  on public.records for delete
  to anon using (true);
