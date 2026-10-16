-- Row Level Security. The mobile app talks to the FastAPI backend for data; the backend connects with a service role
-- that bypasses RLS and enforces ownership/roles itself. These policies are defence in depth for any direct client access:
-- a signed-in user can READ only their own rows, and nobody can write directly from a client.

alter table public.profiles enable row level security;
alter table public.health_profiles enable row level security;
alter table public.consent_records enable row level security;
alter table public.screenings enable row level security;
alter table public.screening_images enable row level security;
alter table public.clinical_reviews enable row level security;
alter table public.products enable row level security;
alter table public.product_variants enable row level security;
alter table public.cart_items enable row level security;
alter table public.orders enable row level security;
alter table public.order_items enable row level security;
alter table public.payments enable row level security;
alter table public.audit_logs enable row level security;   -- no policy at all: invisible to every client

-- Start from zero privileges, then grant read access only where a policy exists.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated, public;
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated, public;

grant select on public.profiles, public.health_profiles, public.consent_records, public.screenings,
  public.screening_images, public.clinical_reviews, public.products, public.product_variants,
  public.cart_items, public.orders, public.order_items, public.payments to authenticated;

create policy profiles_select_own on public.profiles for select to authenticated
  using (id = (select auth.uid()));
create policy health_profiles_select_own on public.health_profiles for select to authenticated
  using (user_id = (select auth.uid()));
create policy consent_records_select_own on public.consent_records for select to authenticated
  using (user_id = (select auth.uid()));
create policy screenings_select_own on public.screenings for select to authenticated
  using (user_id = (select auth.uid()));
create policy screening_images_select_own on public.screening_images for select to authenticated
  using (user_id = (select auth.uid()));
create policy clinical_reviews_select_own on public.clinical_reviews for select to authenticated
  using (exists (select 1 from public.screenings s where s.id = screening_id and s.user_id = (select auth.uid())));

create policy products_select_active on public.products for select to authenticated
  using (active);
create policy product_variants_select_active on public.product_variants for select to authenticated
  using (exists (select 1 from public.products p where p.id = product_id and p.active));

create policy cart_items_select_own on public.cart_items for select to authenticated
  using (user_id = (select auth.uid()));
create policy orders_select_own on public.orders for select to authenticated
  using (user_id = (select auth.uid()));
create policy order_items_select_own on public.order_items for select to authenticated
  using (exists (select 1 from public.orders o where o.id = order_id and o.user_id = (select auth.uid())));
create policy payments_select_own on public.payments for select to authenticated
  using (exists (select 1 from public.orders o where o.id = order_id and o.user_id = (select auth.uid())));

-- Deliberately absent: INSERT / UPDATE / DELETE policies. In particular nobody can change profiles.role,
-- orders, payments, screening outcomes or clinical reviews from a client. Admin and clinical-reviewer access
-- (which never includes photos for admins) is enforced in the backend and audited.
