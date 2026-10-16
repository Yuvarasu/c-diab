-- C-Diab schema (PostgreSQL / Supabase). Mirrors backend/app/models.py.
-- All writes go through the FastAPI backend (service connection). Clients only ever read, via RLS (see next migration).

create table public.profiles (
  id uuid primary key,                      -- equals auth.users.id; intentionally no FK so deleting the auth user keeps anonymised order records
  email text,
  full_name text,
  phone text,
  date_of_birth date,
  role text not null default 'customer' check (role in ('customer', 'admin', 'clinical_reviewer')),
  created_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table public.health_profiles (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  diabetes_type text check (diabetes_type in ('type1', 'type2', 'gestational', 'other', 'not_sure')),
  diabetes_duration_years integer check (diabetes_duration_years between 0 and 80),
  prior_foot_ulcer text check (prior_foot_ulcer in ('yes', 'no', 'not_sure')),
  foot_surgery_or_amputation text check (foot_surgery_or_amputation in ('yes', 'no', 'not_sure')),
  current_symptoms_note text check (char_length(current_symptoms_note) <= 1000),
  updated_at timestamptz not null default now()
);

-- Append-only consent history; the latest row per consent_type wins. ai_training is separate and optional.
create table public.consent_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  consent_type text not null check (consent_type in ('terms', 'health_data_processing', 'image_screening', 'ai_training')),
  granted boolean not null,
  policy_version text not null,
  created_at timestamptz not null default now()
);
create index ix_consent_records_user_id on public.consent_records (user_id);

create table public.screenings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'draft' check (status in ('draft', 'completed', 'failed')),
  symptoms jsonb not null default '{}'::jsonb,
  triage_level text not null check (triage_level in ('routine', 'caution', 'urgent')),
  triage_reasons jsonb not null default '[]'::jsonb,
  outcome text check (outcome in ('no_obvious_wound', 'possible_superficial_wound', 'possible_deeper_wound',
                                  'inconclusive_image', 'clinical_review_required', 'urgent_warning')),
  image_quality_ok boolean,
  quality_issues jsonb not null default '[]'::jsonb,
  wound_detected boolean,
  category text check (category in ('superficial', 'deep')),
  confidence double precision check (confidence between 0 and 1),
  model_name text,
  model_version text,
  is_demo boolean not null default false,
  requires_clinical_review boolean not null default false,
  assigned_reviewer_id uuid references public.profiles (id) on delete set null,
  policy_version text not null,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);
create index ix_screenings_user_id on public.screenings (user_id);
create index ix_screenings_reviewer on public.screenings (assigned_reviewer_id) where assigned_reviewer_id is not null;

create table public.screening_images (
  id uuid primary key default gen_random_uuid(),
  screening_id uuid not null references public.screenings (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  side text not null check (side in ('left', 'right')),
  storage_path text not null,               -- {user_id}/{screening_id}/{side}-{random}.jpg, always server generated
  size_bytes integer not null,
  width integer not null,
  height integer not null,
  quality jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (screening_id, side)
);
create index ix_screening_images_screening_id on public.screening_images (screening_id);
create index ix_screening_images_user_id on public.screening_images (user_id);

create table public.clinical_reviews (
  id uuid primary key default gen_random_uuid(),
  screening_id uuid not null references public.screenings (id) on delete cascade,
  reviewer_id uuid not null references public.profiles (id),
  decision text not null check (decision in ('approved_for_footwear', 'not_suitable', 'needs_in_person_assessment')),
  notes text,
  created_at timestamptz not null default now()
);
create index ix_clinical_reviews_screening_id on public.clinical_reviews (screening_id);

create table public.products (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  description text not null default '',
  intended_use text not null default '',
  materials text not null default '',
  care_instructions text not null default '',
  shipping_info text not null default '',
  return_info text not null default '',
  price_paise integer not null check (price_paise >= 0),
  image_urls jsonb not null default '[]'::jsonb,
  requires_screening boolean not null default true,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.product_variants (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products (id) on delete cascade,
  size text not null,
  sku text,
  stock integer not null default 0 check (stock >= 0),   -- the database itself refuses to oversell
  price_override_paise integer check (price_override_paise >= 0),
  unique (product_id, size)
);
create index ix_product_variants_product_id on public.product_variants (product_id);

create table public.cart_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  variant_id uuid not null references public.product_variants (id) on delete cascade,
  quantity integer not null check (quantity > 0),
  created_at timestamptz not null default now(),
  unique (user_id, variant_id)
);
create index ix_cart_items_user_id on public.cart_items (user_id);

create table public.orders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id),      -- restrict: order records are retained after account deletion
  screening_id uuid references public.screenings (id) on delete set null,
  status text not null default 'pending_payment' check (status in
    ('pending_payment', 'payment_failed', 'paid', 'processing', 'shipped', 'delivered', 'cancelled')),
  subtotal_paise integer not null check (subtotal_paise >= 0),
  shipping_paise integer not null check (shipping_paise >= 0),
  total_paise integer not null check (total_paise >= 0),
  currency text not null default 'INR',
  shipping_name text not null,
  shipping_phone text not null,
  address jsonb not null default '{}'::jsonb,
  delivery_instructions text,
  idempotency_key text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, idempotency_key)                            -- duplicate checkout requests cannot create two orders
);
create index ix_orders_user_id on public.orders (user_id);

create table public.order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete cascade,
  variant_id uuid references public.product_variants (id) on delete set null,
  product_name text not null,
  size text not null,
  unit_price_paise integer not null check (unit_price_paise >= 0),
  quantity integer not null check (quantity > 0)
);
create index ix_order_items_order_id on public.order_items (order_id);

create table public.payments (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete cascade,
  provider text not null,
  provider_order_id text not null,
  provider_payment_id text,
  status text not null default 'created' check (status in ('created', 'paid', 'failed')),
  amount_paise integer not null check (amount_paise >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, provider_payment_id)                       -- one gateway payment can only ever settle one order
);
create index ix_payments_order_id on public.payments (order_id);
create index ix_payments_provider_order_id on public.payments (provider_order_id);

create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid,
  action text not null,
  entity_type text not null,
  entity_id text,
  metadata jsonb not null default '{}'::jsonb,                 -- never put health details here
  created_at timestamptz not null default now()
);
create index ix_audit_entity on public.audit_logs (entity_type, entity_id);

-- Keep updated_at honest even for manual SQL edits.
create function public.set_updated_at() returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at = now(); return new; end $$;
create trigger trg_health_profiles_updated before update on public.health_profiles for each row execute function public.set_updated_at();
create trigger trg_products_updated before update on public.products for each row execute function public.set_updated_at();
create trigger trg_orders_updated before update on public.orders for each row execute function public.set_updated_at();
create trigger trg_payments_updated before update on public.payments for each row execute function public.set_updated_at();

-- New sign-ups get a customer profile. Roles are never taken from user-editable metadata.
create function public.handle_new_user() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, nullif(new.raw_user_meta_data ->> 'full_name', ''))
  on conflict (id) do nothing;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();
