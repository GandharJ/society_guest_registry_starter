# Society Guest Registry — starter project

A mobile-first visitor management system scaffold:
- Flutter mobile client (Android/iOS)
- Python FastAPI REST backend
- PostgreSQL database
- JWT authentication foundation
- Visitor registration, approval, check-in and check-out API foundations

## Architecture

Flutter app -> HTTPS/REST -> FastAPI -> PostgreSQL
                                      -> Firebase Cloud Messaging (planned integration)

## Project structure

```text
society_guest_registry/
  backend/
    app/
      main.py
      database.py
      models.py
      schemas.py
      security.py
    requirements.txt
    .env.example
    Dockerfile
  mobile/
    pubspec.yaml
    lib/main.dart
  docker-compose.yml
```

## 1. Start PostgreSQL and the API

Install Docker Desktop, then from this folder:

```bash
docker compose up --build
```

API documentation: http://localhost:8000/docs

The backend creates database tables on startup. This is a development scaffold;
use Alembic migrations before production deployment.

## 2. Create the first administrator

For this starter, create an admin account using the API's `/auth/register` endpoint.
For a real deployment, disable public registration and create users through a
restricted admin invitation workflow.

Example request:

```json
{
  "name": "Society Admin",
  "email": "admin@example.com",
  "password": "ChangeThis-StrongPassword",
  "role": "admin",
  "flat_number": null
}
```

Then use `/auth/login` to obtain a bearer token. In Swagger UI, click **Authorize**
and enter the token as `Bearer <token>`.

Roles: `admin`, `guard`, `resident`.

## 3. API workflow

1. Admin creates resident and guard accounts (registration is open only in this
   development starter; lock it down before deployment).
2. Guard creates a visitor record with `POST /visitors`.
3. Resident approves/rejects with `POST /visitors/{id}/decision`.
4. Guard records entry with `POST /visitors/{id}/check-in`.
5. Guard records exit with `POST /visitors/{id}/check-out`.
6. Admin/guard can list visit records with `GET /visitors`.

All visitor endpoints require a JWT. The starter includes role checks for
approval and gate operations; extend flat-level authorization before production.

## 4. Run the Flutter app

Install Flutter SDK, then:

```bash
cd mobile
flutter pub get
flutter run
```

For Android emulator use `http://10.0.2.2:8000`; for iOS simulator use
`http://127.0.0.1:8000`. A physical phone must use your computer's LAN IP,
and the API must be reachable on that network.

The included Flutter screen is a connectivity/dashboard starter. The next
implementation stage is role-based login, visitor form, approval inbox,
QR scanning and push notifications.

## Production checklist

- Enforce HTTPS and secure secret management; rotate `SECRET_KEY`.
- Close public registration; use admin-created invitations.
- Add per-society tenancy and strict flat-level authorization.
- Add Alembic migrations, backups, monitoring and rate limiting.
- Store visitor photos in private object storage, not public URLs.
- Add consent/notice, retention limits and deletion procedures for personal data.
- Use signed, short-lived, single-use QR tokens; never encode personal details in QR.
- Integrate Firebase Admin SDK for push notifications.
- Add audit events for approvals, edits and check-in/check-out.
- Obtain society approval and review applicable Indian privacy requirements
  before collecting visitor personal data.
