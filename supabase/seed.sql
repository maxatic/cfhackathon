insert into public.tenants (id, external_id, name) values
  ('11111111-1111-4111-8111-111111111111', 'tenant_northstar', 'Northstar Industrial'),
  ('22222222-2222-4222-8222-222222222222', 'tenant_apex', 'Apex Distribution')
on conflict (external_id) do nothing;

insert into public.products (id, tenant_id, sku, name, category, unit_price) values
  ('aaaaaaaa-0001-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111', 'NSI-VAL-100', 'Valves Kit 1', 'valves', 184.00),
  ('aaaaaaaa-0002-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111', 'NSI-PUM-101', 'Pumps Kit 2', 'pumps', 292.00),
  ('aaaaaaaa-0003-4000-8000-000000000003', '11111111-1111-4111-8111-111111111111', 'NSI-FIL-102', 'Filters Kit 3', 'filters', 88.00),
  ('bbbbbbbb-0001-4000-8000-000000000001', '22222222-2222-4222-8222-222222222222', 'APX-VAL-100', 'Valves Kit 1', 'valves', 176.00),
  ('bbbbbbbb-0002-4000-8000-000000000002', '22222222-2222-4222-8222-222222222222', 'APX-SEN-101', 'Sensors Kit 2', 'sensors', 126.00)
on conflict (tenant_id, sku) do nothing;

insert into public.customers (id, tenant_id, external_ref, name, segment, region) values
  ('cccccccc-0001-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111', 'cust_001', 'Atlas Manufacturing', 'enterprise', 'North America'),
  ('cccccccc-0002-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111', 'cust_002', 'Beacon Supply', 'wholesale', 'EMEA'),
  ('cccccccc-0003-4000-8000-000000000003', '11111111-1111-4111-8111-111111111111', 'cust_003', 'Cobalt Works', 'regional', 'APAC'),
  ('dddddddd-0001-4000-8000-000000000001', '22222222-2222-4222-8222-222222222222', 'cust_001', 'Delta Assembly', 'enterprise', 'EMEA'),
  ('dddddddd-0002-4000-8000-000000000002', '22222222-2222-4222-8222-222222222222', 'cust_002', 'Evergreen Logistics', 'wholesale', 'APAC')
on conflict (tenant_id, external_ref) do nothing;

insert into public.orders (
  tenant_id,
  product_id,
  customer_id,
  order_date,
  quantity,
  unit_price,
  promotion,
  stockout,
  lead_time_days
)
select
  product.tenant_id,
  product.id,
  customer.id,
  date '2024-01-01' + (week_index * 7),
  greatest(
    1,
    round(
      (
        case customer.segment
          when 'enterprise' then 72
          when 'wholesale' then 48
          else 31
        end
        * (1 + (sin(week_index::numeric / 8.0) * 0.18))
        * case when week_index % 13 in (11, 12) then 1.22 else 1 end
        * case when week_index % 41 = 0 then 0.58 else 1 end
      )
    )::integer
  ),
  product.unit_price,
  week_index % 13 in (11, 12),
  week_index % 41 = 0,
  5 + (week_index % 12) + case when week_index % 41 = 0 then 7 else 0 end
from public.products product
join public.customers customer on customer.tenant_id = product.tenant_id
cross join generate_series(0, 103) as week_index
on conflict do nothing;

insert into public.model_versions (id, tenant_id, version_label, model_name, metrics, artifact_uri, status, trained_at) values
  (
    'eeeeeeee-0001-4000-8000-000000000001',
    '11111111-1111-4111-8111-111111111111',
    'model_demo_seed',
    'mini-transformer-v1',
    '{"mae": 18.4, "smape": 8.7, "holdout_weeks": 8}',
    'container://services/mcp',
    'active',
    now()
  ),
  (
    'eeeeeeee-0002-4000-8000-000000000002',
    '22222222-2222-4222-8222-222222222222',
    'model_demo_apex',
    'mini-transformer-v1',
    '{"mae": 21.6, "smape": 9.8, "holdout_weeks": 8}',
    'container://services/mcp',
    'active',
    now()
  )
on conflict (tenant_id, version_label) do nothing;

insert into public.billing_status (tenant_id, plan, status, current_period_end) values
  ('11111111-1111-4111-8111-111111111111', 'hackathon', 'active', now() + interval '30 days'),
  ('22222222-2222-4222-8222-222222222222', 'hackathon', 'active', now() + interval '30 days')
on conflict (tenant_id) do nothing;
