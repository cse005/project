# Farmer Support Platform 🌾

A Django-based platform for farmers and rural service providers (labor, tractor, tools, lease, and pesticide/fertilizer shops) with OTP login, role dashboards, bookings, and location-aware workflows.

## Features
- OTP-based registration and login flow
- Multi-role service marketplace (farmer + providers)
- Booking lifecycle (request, accept/reject, track)
- Cart/checkout flow for pesticide shop orders
- Pincode-based district/mandal/village lookup APIs
- Admin analytics dashboard

## Tech Stack
- Python 3.12+
- Django 6
- SQLite (default) / PostgreSQL (production)
- Bootstrap + vanilla JavaScript

## Quick Start (Local)
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure environment variables (copy `.env.example` if available).
4. Run migrations:
   ```bash
   python manage.py migrate
   ```
5. Start development server:
   ```bash
   python manage.py runserver
   ```

## Required Environment Variables
- `DJANGO_SECRET_KEY` (required unless using local insecure override)
- `DJANGO_DEBUG` (`true`/`false`)
- `DJANGO_ALLOWED_HOSTS` (required when debug is false)

### Local convenience for checks/tests
For local checks without a production secret key:
```bash
DJANGO_ALLOW_INSECURE_DEV_KEY=true DJANGO_DEBUG=true DJANGO_ALLOWED_HOSTS=localhost python manage.py check
```

## OTP and Security Notes
- OTP requests and login attempts are rate limited.
- OTP expiration/attempt windows are configurable via settings environment variables.
- Production should run behind HTTPS with secure cookie settings enabled.

## Common Commands
```bash
# run tests
DJANGO_ALLOW_INSECURE_DEV_KEY=true DJANGO_DEBUG=true DJANGO_ALLOWED_HOSTS=localhost python manage.py test

# Django system checks
DJANGO_ALLOW_INSECURE_DEV_KEY=true DJANGO_DEBUG=true DJANGO_ALLOWED_HOSTS=localhost python manage.py check

# generate API docs command output (project-specific)
python manage.py generate_api_docs
```

## Production Checklist
- Set `DJANGO_ENV=production`
- Set `DJANGO_DEBUG=false`
- Set strong `DJANGO_SECRET_KEY`
- Configure non-SQLite DB settings (`DJANGO_DB_*`)
- Configure `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`
- Run `python manage.py collectstatic`
