-- SlotPay M1: schema, overlap guard, RLS.
create extension if not exists btree_gist;
create extension if not exists pgcrypto;

create or replace function set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

create type booking_status as enum ('held','confirmed','completed','cancelled','no_show','expired');

create table business (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  address text not null default '',
  phone text not null default '',
  email text not null default '',
  maps_url text not null default '',
  timezone text not null default 'Asia/Kolkata',
  slot_step_min int not null default 15 check (slot_step_min > 0),
  min_lead_min int not null default 60 check (min_lead_min >= 0),
  max_advance_days int not null default 30 check (max_advance_days > 0),
  hold_minutes int not null default 10 check (hold_minutes > 0),
  cancellation_cutoff_hours int not null default 4 check (cancellation_cutoff_hours >= 0),
  advance_applies text not null default 'always' check (advance_applies in ('always','weekends_and_holidays')),
  policy_text text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table business_holiday (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references business(id) on delete cascade,
  date date not null,
  reason text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_id, date)
);

create table service (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references business(id) on delete cascade,
  category text not null check (category in ('hair','skin','nails','spa')),
  name text not null,
  description text not null default '',
  duration_min int not null check (duration_min > 0),
  price_paise int not null check (price_paise >= 0),   -- GST-inclusive
  advance_type text not null default 'none' check (advance_type in ('none','fixed','percent')),
  advance_value int not null default 0 check (advance_value >= 0), -- paise if fixed, percent if percent
  buffer_min int not null default 0 check (buffer_min >= 0),
  is_active boolean not null default true,
  sort_order int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_id, name)
);

create table staff (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references business(id) on delete cascade,
  name text not null,
  title text not null default '',
  avatar_url text not null default '',
  bio text not null default '',
  is_active boolean not null default true,
  shift_template jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_id, name)
);

create table staff_service (
  staff_id uuid not null references staff(id) on delete cascade,
  service_id uuid not null references service(id) on delete cascade,
  primary key (staff_id, service_id)
);

create table time_block (
  id uuid primary key default gen_random_uuid(),
  staff_id uuid not null references staff(id) on delete cascade,
  time_range tstzrange not null check (not isempty(time_range)),
  reason text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index time_block_range_idx on time_block using gist (staff_id, time_range);

create table customer (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references business(id) on delete cascade,
  name text not null,
  phone_e164 text not null check (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  whatsapp_opt_in boolean not null default false,
  consent_source text not null default '',
  skip_advance boolean not null default false,
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_id, phone_e164)
);

-- Staff users for admin; id mirrors Supabase auth.users.id (no FK so plain Postgres works in tests).
create table staff_user (
  id uuid primary key,
  business_id uuid not null references business(id) on delete cascade,
  email text not null,
  role text not null check (role in ('owner','front_desk')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table booking (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references business(id),
  customer_id uuid not null references customer(id),
  service_id uuid not null references service(id),
  staff_id uuid not null references staff(id),
  time_range tstzrange not null,          -- what the customer sees
  block_range tstzrange not null,         -- time_range extended by the service buffer
  status booking_status not null default 'held',
  hold_expires_at timestamptz,
  source text not null default 'online' check (source in ('online','walk_in','phone')),
  price_paise int not null check (price_paise >= 0),
  advance_due_paise int not null default 0 check (advance_due_paise >= 0),
  advance_paid_paise int not null default 0 check (advance_paid_paise >= 0),
  public_token text not null unique,
  cancelled_at timestamptz,
  cancel_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint booking_range_valid check (not isempty(time_range) and block_range @> time_range),
  constraint booking_no_overlap exclude using gist (
    staff_id with =,
    block_range with &&
  ) where (status not in ('cancelled','expired'))
);
create index booking_business_time_idx on booking using gist (business_id, time_range);
create index booking_hold_idx on booking (hold_expires_at) where status = 'held';
create index booking_customer_idx on booking (customer_id);

-- Bookings may not overlap staff time blocks (breaks/leave/admin blocks).
-- Chosen: trigger (not a cross-table exclusion, which Postgres cannot express).
-- Same-transaction check; concurrent block inserts are guarded symmetrically below.
create or replace function booking_check_time_block() returns trigger language plpgsql as $$
begin
  if new.status in ('cancelled','expired') then return new; end if;
  perform pg_advisory_xact_lock(hashtextextended(new.staff_id::text, 0));
  if exists (select 1 from time_block tb where tb.staff_id = new.staff_id and tb.time_range && new.time_range) then
    raise exception 'booking overlaps a time block' using errcode = '23P01', constraint = 'booking_vs_time_block';
  end if;
  return new;
end $$;
create trigger booking_time_block_guard before insert or update of staff_id, time_range, status on booking
  for each row execute function booking_check_time_block();

create or replace function time_block_check_booking() returns trigger language plpgsql as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(new.staff_id::text, 0));
  if exists (select 1 from booking b where b.staff_id = new.staff_id
             and b.status not in ('cancelled','expired') and b.time_range && new.time_range) then
    raise exception 'time block overlaps an existing booking' using errcode = '23P01', constraint = 'time_block_vs_booking';
  end if;
  return new;
end $$;
create trigger time_block_booking_guard before insert or update of staff_id, time_range on time_block
  for each row execute function time_block_check_booking();

create table payment (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references booking(id) on delete cascade,
  razorpay_order_id text not null unique,
  razorpay_payment_id text unique,
  amount_paise int not null check (amount_paise >= 0),
  status text not null default 'created'
    check (status in ('created','authorized','captured','failed','refunded','partially_refunded')),
  method text,
  refunded_paise int not null default 0 check (refunded_paise >= 0),
  is_seeded boolean not null default false,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table refund (
  id uuid primary key default gen_random_uuid(),
  payment_id uuid not null references payment(id) on delete cascade,
  razorpay_refund_id text not null unique,
  amount_paise int not null check (amount_paise > 0),
  status text not null default 'initiated',
  reason text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table webhook_event (
  id text primary key,
  source text not null check (source in ('razorpay','whatsapp')),
  event text not null default '',
  payload jsonb not null default '{}'::jsonb,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table scheduled_message (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references booking(id) on delete cascade,
  kind text not null check (kind in ('confirmation','remind_24h','remind_2h','cancelled','refund')),
  send_at timestamptz not null,
  status text not null default 'pending' check (status in ('pending','sent','skipped','failed')),
  attempts int not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (booking_id, kind)
);
create index scheduled_message_due_idx on scheduled_message (send_at) where status = 'pending';

create table message_log (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid references booking(id) on delete set null,
  customer_id uuid references customer(id) on delete set null,
  direction text not null check (direction in ('in','out')),
  channel text not null check (channel in ('whatsapp','simulator')),
  template text,
  body text not null default '',
  buttons jsonb,
  provider_message_id text,
  status text not null default 'queued',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table audit_event (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references business(id) on delete cascade,
  booking_id uuid references booking(id) on delete set null,
  type text not null,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index audit_event_business_time_idx on audit_event (business_id, created_at desc);

-- updated_at triggers
do $$
declare t text;
begin
  for t in select c.table_name from information_schema.columns c
           join information_schema.tables tb on tb.table_name = c.table_name and tb.table_schema = c.table_schema
           where c.table_schema = 'public' and c.column_name = 'updated_at' and tb.table_type = 'BASE TABLE'
  loop
    execute format('create trigger %I before update on %I for each row execute function set_updated_at()', t || '_updated_at', t);
  end loop;
end $$;

-- RLS: enabled everywhere, deliberately NO policies. anon/authenticated roles get nothing;
-- the API connects with a privileged server-side role (bypasses RLS) and is the only writer.
do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'public'
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;
