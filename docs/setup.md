# Setup

Prerequisites: Node 22+, Python 3.12+, a free Supabase project, (for builds) an Expo account.

## 1. Supabase
1. Create a project. Note the **Project URL**, the **publishable (anon) key**, the **service-role key** (secret!) and the **Postgres connection string** (Settings → Database).
2. Auth → Providers: enable Email. Decide whether email confirmation is required (the app handles both).
3. Auth → URL Configuration: set the Site URL / redirect for password-recovery emails to a page you host (the app sends the reset email; completing the reset happens on that page).
4. Apply the migrations **in order**, in the SQL editor or with `psql "$DATABASE_URL" -f ...`:
   `database/migrations/20261011000001_schema.sql` → `..._rls_policies.sql` → `..._storage.sql`. Optionally `database/seed.sql` for sample products.
5. JWT verification: new projects use asymmetric signing keys → leave `SUPABASE_JWT_SECRET` empty (the backend uses the project's JWKS). Legacy projects: put the JWT secret in `SUPABASE_JWT_SECRET`.
   *Note: JWKS verification is implemented but could not be tested against a live Supabase project in the development sandbox. Test it with a real login before relying on it.*

### Giving someone a role
Everyone starts as `customer`. Roles are changed only in SQL:
```sql
update public.profiles set role = 'admin'             where email = 'you@example.com';
update public.profiles set role = 'clinical_reviewer' where email = 'doctor@example.com';
```

## 2. Backend

**Windows (PowerShell)** (needs Python 3.11 or newer from python.org, with "Add python.exe to PATH" ticked):
```powershell
cd backend
py -3 -m venv .venv                      # or: python -m venv .venv
.\.venv\Scripts\Activate.ps1             # if PowerShell blocks it:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m pip install -r requirements-dev.txt
Copy-Item .env.demo.example .env         # then open .env and set SUPABASE_URL
python -m app.seed
python -m uvicorn app.main:create_app --factory --reload --port 8000
```
Check it works: open http://127.0.0.1:8000/health (and http://127.0.0.1:8000/docs). Always start the server with `python -m uvicorn`; a bare `uvicorn` command only works if Python's Scripts folder is on your PATH. Windows PowerShell 5.1 has no `&&`: run the lines one at a time.

**macOS / Linux:**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.demo.example .env       # fill in SUPABASE_URL; see .env.example for every option
python -m app.seed              # sample products (local SQLite); skip when using the SQL seed
python -m uvicorn app.main:create_app --factory --reload --port 8000
```
**Demo-friendly local configuration** (shows the whole journey with the labelled demo AI):
`APP_ENV=development  POLICY_CONFIG_PATH=policy/policy.demo.json  ALLOW_DEMO_ELIGIBILITY=true  AI_BACKEND=demo  PAYMENT_PROVIDER=mock`

For the **strict** flow (clinician approval required), use the default `policy/policy.default.json`, make two accounts, promote one to `clinical_reviewer` and one to `admin`, then: admin assigns the case (Admin → Clinical review routing), the reviewer approves it, and checkout unlocks.

Deploy with `backend/Dockerfile` behind HTTPS. Production refuses to start with unsafe settings (see `.env.example`).

## 3. Mobile
```bash
cd mobile
npm install
cp .env.example .env            # EXPO_PUBLIC_API_URL, EXPO_PUBLIC_SUPABASE_URL, EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY
npx expo install --check && npx expo-doctor
```
Only **public** values go in the app. `EXPO_PUBLIC_*` variables are baked into the JavaScript bundle, so never put the service-role key or any payment secret there. Build and install the custom development build with `docs/android_build.md`, then `npx expo start --dev-client`. **Expo Go is not used.**
`EXPO_PUBLIC_API_URL` must be reachable from the phone (your computer's LAN address for local work, an HTTPS URL for preview/production builds; Android blocks cleartext HTTP in release builds).

## 4. Verify
| Command | Proves |
|---|---|
| `cd backend && pytest -q` | 121 backend tests (policy, auth, screening, orders, payments, admin/clinical, privacy) |
| `pip install -r requirements-pgverify.txt` then `python scripts/pg_verify.py` | migrations apply on real PostgreSQL; RLS / storage rules / constraints hold; the same 121 tests pass against the SQL schema |
| `python scripts/e2e_smoke.py http://127.0.0.1:8000` | full journey over real HTTP against a running server (needs the server's `SUPABASE_JWT_SECRET` in your environment) |
| `cd mobile && npm run typecheck && npm test` | 0 type errors (incl. typed routes); 27 mobile tests |
| `npx expo export --platform android` | the Android bundle compiles |
