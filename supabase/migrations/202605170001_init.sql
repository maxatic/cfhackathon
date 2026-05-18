create extension if not exists pgcrypto;

create table public.tenants (
  id uuid primary key default gen_random_uuid(),
  external_id text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);

create table public.profiles (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  user_id uuid not null unique,
  role text not null check (role in ('owner', 'planner', 'viewer')),
  display_name text not null,
  created_at timestamptz not null default now()
);

create table public.products (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  sku text not null,
  name text not null,
  category text not null,
  unit_price numeric(12, 2) not null check (unit_price >= 0),
  created_at timestamptz not null default now(),
  unique (tenant_id, sku)
);

create table public.customers (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  external_ref text not null,
  name text not null,
  segment text not null check (segment in ('enterprise', 'wholesale', 'regional')),
  region text not null,
  created_at timestamptz not null default now(),
  unique (tenant_id, external_ref)
);

create table public.orders (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  product_id uuid not null references public.products(id) on delete cascade,
  customer_id uuid not null references public.customers(id) on delete cascade,
  order_date date not null,
  quantity integer not null check (quantity >= 0),
  unit_price numeric(12, 2) not null check (unit_price >= 0),
  promotion boolean not null default false,
  stockout boolean not null default false,
  lead_time_days integer not null check (lead_time_days >= 0),
  created_at timestamptz not null default now()
);

create table public.forecast_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  product_id uuid not null references public.products(id) on delete cascade,
  customer_segment text not null default 'all',
  horizon_weeks integer not null check (horizon_weeks between 1 and 52),
  model_version_id uuid,
  forecast jsonb not null,
  metrics jsonb not null default '{}'::jsonb,
  created_by uuid,
  created_at timestamptz not null default now()
);

create table public.model_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  version_label text not null,
  model_name text not null,
  metrics jsonb not null default '{}'::jsonb,
  artifact_uri text,
  status text not null check (status in ('active', 'archived', 'failed')),
  trained_at timestamptz not null default now(),
  unique (tenant_id, version_label)
);

alter table public.forecast_runs
  add constraint forecast_runs_model_version_fk
  foreign key (model_version_id) references public.model_versions(id) on delete set null;

create table public.retraining_jobs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  requested_by uuid,
  reason text not null,
  status text not null check (status in ('queued', 'running', 'completed', 'failed')),
  model_version_id uuid references public.model_versions(id) on delete set null,
  logs jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table public.api_usage_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  actor_user_id uuid,
  tool_name text not null,
  status text not null check (status in ('ok', 'error', 'denied')),
  latency_ms integer,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.billing_status (
  tenant_id uuid primary key references public.tenants(id) on delete cascade,
  stripe_customer_id text,
  plan text not null default 'hackathon',
  status text not null check (status in ('active', 'trialing', 'past_due', 'canceled')),
  current_period_end timestamptz,
  updated_at timestamptz not null default now()
);

create index orders_tenant_sku_date_idx on public.orders (tenant_id, product_id, order_date);
create index orders_tenant_customer_idx on public.orders (tenant_id, customer_id);
create index forecast_runs_tenant_created_idx on public.forecast_runs (tenant_id, created_at desc);
create index api_usage_events_tenant_created_idx on public.api_usage_events (tenant_id, created_at desc);

create or replace function public.current_tenant_id()
returns uuid
language sql
stable
as $$
  select nullif(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')::uuid;
$$;

alter table public.tenants enable row level security;
alter table public.profiles enable row level security;
alter table public.products enable row level security;
alter table public.customers enable row level security;
alter table public.orders enable row level security;
alter table public.forecast_runs enable row level security;
alter table public.model_versions enable row level security;
alter table public.retraining_jobs enable row level security;
alter table public.api_usage_events enable row level security;
alter table public.billing_status enable row level security;

create policy tenants_select_own on public.tenants
  for select to authenticated
  using (id = public.current_tenant_id());

create policy profiles_select_own_tenant on public.profiles
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

create policy products_select_own_tenant on public.products
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

create policy customers_select_own_tenant on public.customers
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

create policy orders_select_own_tenant on public.orders
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

create policy forecast_runs_select_own_tenant on public.forecast_runs
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

create policy forecast_runs_insert_own_tenant on public.forecast_runs
  for insert to authenticated
  with check (tenant_id = public.current_tenant_id());

create policy model_versions_select_own_tenant on public.model_versions
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

create policy retraining_jobs_select_own_tenant on public.retraining_jobs
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

create policy retraining_jobs_insert_own_tenant on public.retraining_jobs
  for insert to authenticated
  with check (tenant_id = public.current_tenant_id());

create policy api_usage_events_insert_own_tenant on public.api_usage_events
  for insert to authenticated
  with check (tenant_id = public.current_tenant_id());

create policy api_usage_events_select_own_tenant on public.api_usage_events
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

create policy billing_status_select_own_tenant on public.billing_status
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

grant usage on schema public to authenticated;
grant select on public.tenants, public.profiles, public.products, public.customers, public.orders,
  public.forecast_runs, public.model_versions, public.retraining_jobs, public.api_usage_events,
  public.billing_status to authenticated;
grant insert on public.forecast_runs, public.retraining_jobs, public.api_usage_events to authenticated;
