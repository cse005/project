# Project Review & Immediate Next Steps

## What I found

This is a Django-based multi-role agricultural services platform with separate registration/login and dashboards for:
- Farmer
- Tractor provider
- Labor
- Lease owner
- Tools rental
- Pesticide/Fertilizer shop

Core routes are wired through `farmer_project/urls.py` and `kisan1/urls.py`, and most application logic is in `kisan1/views.py` and `kisan1/models.py`.

## What you should do now (priority order)

### 1) Fix environment bootstrapping first (blocking)
The app currently fails on startup checks because `python-dotenv` is imported in settings but missing from `requirements.txt`.

**Action:**
- Add these to `requirements.txt`:
  - `python-dotenv`
  - `dj-database-url`
- Reinstall deps and run:
  - `python manage.py check`
  - `python manage.py test`

### 2) Remove hardcoded secrets and insecure defaults (high priority)
`SECRET_KEY` is hardcoded and `DEBUG=True` with `ALLOWED_HOSTS=['*']`.

**Action:**
- Move `SECRET_KEY`, `DEBUG`, and allowed hosts to environment variables.
- Set secure production defaults:
  - `DEBUG=False`
  - strict `ALLOWED_HOSTS`

### 3) Move sensitive API credentials out of source (high priority)
The OTP SMS authorization token is hardcoded inside `send_real_otp_sms`.

**Action:**
- Read SMS API token from environment variable.
- Add fallback behavior for local/dev without sending real OTP.

### 4) Expand tests beyond smoke checks (high priority)
Current tests only verify a simple model insert and welcome page load.

**Action:**
Add tests for:
- OTP verification success/failure flows
- Role-based redirects and session checks
- Booking creation and status transitions (accept/reject/cancel)
- Cart/shop order stock deduction edge cases

### 5) Add project documentation (medium priority)
There is no README with setup/run instructions.

**Action:**
Create `README.md` with:
- local setup
- environment variables
- migrate/load sample data
- test commands
- role-based demo walkthrough

### 6) Improve data validation and error handling (medium priority)
Several POST flows trust raw request values and parse integers without centralized validation.

**Action:**
- Move form parsing to Django Forms/ModelForms for booking/order flows.
- Add validation for mobile format, quantities, dates, and negative/invalid numeric values.

### 7) Plan small refactor for maintainability (medium priority)
`views.py` is large and mixes concerns.

**Action:**
- Split by domain modules (`auth_views.py`, `booking_views.py`, `dashboard_views.py`, etc.)
- Extract shared helpers/services (OTP, pricing calc, inventory updates).

## Suggested “next 2 days” execution plan

### Day 1
1. Dependency fix (`python-dotenv`, `dj-database-url`) and green `manage.py check`.
2. Security/env hardening (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, SMS token).
3. Add minimal README + `.env.example`.

### Day 2
1. Add tests for login/OTP + 2 booking flows.
2. Add tests for shop order stock deduction.
3. Start splitting large views file into modules.

## Definition of done for this phase
- App boots with `python manage.py check` successfully.
- Tests run and cover key auth + booking + inventory paths.
- No secrets/tokens hardcoded in repo.
- New developer can run project from README in <15 minutes.
