# Architecture Overview

## Application Structure

- `farmer_project/` contains Django project configuration, middleware registration, and environment-driven deployment settings.
- `kisan1/views/auth_views.py` handles registration/login with OTP verification.
- `kisan1/views/booking_views.py` handles farmer/provider booking workflows.
- `kisan1/views/location_views.py` serves pincode lookup APIs.
- `kisan1/services.py` contains transaction-safe business logic for booking/order creation and status updates.
- `kisan1/location_service.py` manages pincode dataset bootstrap and cached location lookup.

## Security Controls

- Strict env-based `SECRET_KEY` handling and production checks in settings.
- OTP request throttling + login attempt throttling in cache.
- OTP TTL/expiry validation.
- Session activity expiry and role-locking middleware.
- Global exception logging middleware for safer API failures.
- Request audit logging middleware for observability.

## Data & Performance

- Added model indexes for common lookup paths (`mobile+role`, order timeline lookups, pincode filtering).
- Location lookup uses in-memory cache to avoid repeated DB scans.
- Home/dashboards use pagination for larger result sets.

## Future Enhancements

- Move async or long-running jobs (bulk imports, notification retries) to background workers (Celery/RQ).
- Introduce explicit REST layer + schema validation and API versioning when public API surface expands.
