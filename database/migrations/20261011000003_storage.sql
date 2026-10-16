-- Private bucket for foot photos. The backend (service role) is the only writer; it validates and re-encodes every
-- upload and generates the path itself: {user_id}/{screening_id}/{side}-{random}.jpg
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('screening-images', 'screening-images', false, 8388608, array['image/jpeg'])
on conflict (id) do update
  set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

-- A signed-in user may read objects only inside their own folder. No insert/update/delete policies exist,
-- so a client can neither upload to, overwrite, nor delete from the bucket.
create policy "screening images: owner can read own folder" on storage.objects for select to authenticated
  using (bucket_id = 'screening-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
