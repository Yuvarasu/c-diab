-- Sample catalogue for development. Product copy is PLACEHOLDER text: replace it with approved content before launch.
insert into public.products (slug, name, description, intended_use, materials, care_instructions, shipping_info, return_info, price_paise)
values
 ('cdiab-comfort-step', 'C-Diab Comfort Step Slipper',
  'SAMPLE DATA for development. Replace with approved product copy before launch.',
  'Indoor foot protection as part of a clinician-guided foot-care routine. Not a treatment for foot ulcers.',
  'Placeholder. Confirm materials with the manufacturer.', 'Placeholder. Wipe clean with a damp cloth; air dry.',
  'Placeholder. Confirm shipping times and charges.', 'Placeholder. Confirm the return policy.', 149900),
 ('cdiab-cushion-plus', 'C-Diab Cushion Plus Slipper',
  'SAMPLE DATA for development. Replace with approved product copy before launch.',
  'Indoor foot protection as part of a clinician-guided foot-care routine. Not a treatment for foot ulcers.',
  'Placeholder. Confirm materials with the manufacturer.', 'Placeholder. Wipe clean with a damp cloth; air dry.',
  'Placeholder. Confirm shipping times and charges.', 'Placeholder. Confirm the return policy.', 199900)
on conflict (slug) do nothing;

insert into public.product_variants (product_id, size, sku, stock)
select p.id, 'UK ' || n, p.slug || '-uk' || n, 20
from public.products p cross join generate_series(6, 10) as n
on conflict (product_id, size) do nothing;
