# Society Guest Registry — role-based mobile starter

## Stack
- Flutter mobile app (Android/iOS)
- Python FastAPI backend
- PostgreSQL database
- JWT authentication; role-based access: admin, guard, resident
- Flutter secure storage for saved login token

## Start backend
Install Docker Desktop. Copy `backend/.env.example` to `backend/.env`, replace
`SECRET_KEY` with a long random secret (for example `openssl rand -hex 32`). The
`.env` file is git-ignored, so keep it out of commits. Then run:

```bash
docker compose up --build
```

API docs: http://localhost:8000/docs

## Create accounts
The first account is created once using `POST /auth/register` with role `admin`.
After that, public registration is closed. Admin creates guard/resident accounts
using `POST /admin/users`. Resident accounts require `flat_number`.

Login at `/auth/login`. The Flutter app uses the returned role to show the
appropriate home screen.

**Quick dev data (optional):** instead of calling the endpoints by hand, seed a demo
society with an admin, guard and resident (`admin@example.com`, `guard@example.com`,
`resident@example.com`, flat `A-101`) sharing one password you choose:

```bash
docker compose exec -e SEED_PASSWORD='choose-a-long-dev-password' api python -m app.seed
```

Development only. Never use shared seeded passwords in a real deployment.

## Run mobile app
The repo ships only `lib/` and `pubspec.yaml`. Generate the Android/iOS project
folders once (this keeps the existing `lib/` and `pubspec.yaml`):

```bash
cd mobile
flutter create . --project-name society_guest_registry --platforms=android,ios
flutter pub get
flutter run
```
Android emulator API URL defaults to `http://10.0.2.2:8000`.
For iOS simulator use `--dart-define=API_BASE_URL=http://127.0.0.1:8000`.
For a physical phone, use your computer's LAN IP and ensure both devices share
the same network. Use HTTPS outside local development.

## Implemented
- Role-based login and session restoration
- Guard/admin visitor registration
- Resident approval/rejection
- Guard/admin check-in and check-out
- Role-filtered resident visitor list
- Dashboard summary API

## Still to build
QR pass generation and secure one-time validation, FCM push notifications,
admin user-management screens, audit log, photo storage, analytics/export,
automated tests and production deployment.

## Production requirements
This is a development starter, not production-ready. Add Alembic migrations,
strict society-level tenancy, rate limiting, HTTPS, secret rotation, backups,
audit logging, consent and retention policies, and a reviewed privacy/security
design before collecting real visitor data. QR codes must contain signed,
short-lived opaque tokens—not personal information.


## Version 0.3 additions
- Society, building and flat tables
- Admin endpoints to create society structure and user accounts
- Society-scoped visitor listing and dashboard queries
- Opaque QR tokens: raw token returned once; only SHA-256 hash stored
- QR pass expiry (12 hours) and single-use gate scan endpoint
- CSV visitor report endpoint

## New API sequence
1. Bootstrap the first admin with `POST /auth/register`.
2. Create a society using `POST /admin/societies`. This links the admin to the new
   society automatically (an admin manages one society; a second call returns 409).
3. Create buildings with `POST /admin/buildings`, then flats with `POST /admin/flats`.
4. Create guard/resident accounts using `POST /admin/users`.
5. Issue a pass with `POST /visitors/{id}/qr-pass`; render returned `qr_token` as QR.
6. Gate app submits scanned token to `POST /gate/scan/{qr_token}`.
7. Download `GET /reports/visitors.csv`.

**Important:** FCM push delivery and native QR camera scanning are integration
tasks, not yet wired into this scaffold. The backend endpoints and secure token
lifecycle are present. This remains a development scaffold; add migrations, tests,
strict tenant checks and deployment hardening.
