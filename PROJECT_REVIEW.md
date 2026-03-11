# Django Project Review: Faults, Gaps, and Improvement Plan

## Scope Reviewed
- Core domain/data model: `kisan1/models.py`
- Auth/OTP/session flow: `kisan1/views/auth_views.py`, `kisan1/views/shared.py`, `kisan1/middleware.py`
- Location loading/API behavior: `kisan1/views/location_views.py`, `kisan1/management/commands/load_pincodes.py`
- App configuration and deployment readiness: `farmer_project/settings.py`, `requirements.txt`, `README.md`
- Routing/API surface: `kisan1/urls.py`, `farmer_project/urls.py`

---

## Findings for Requested Issues

### 1) Mobile number should support multiple roles for same user
**Status: Partially addressed, but data model is still account-fragmented.**

- `UserRegistration` uses `unique_together = ('mobile', 'role')`, which allows the same mobile for multiple roles.
- This solves the immediate "one mobile only" constraint, but it creates separate user rows per role instead of one principal identity with many roles.

**Risk/impact**
- Fragmented profiles/sessions per role.
- Harder identity management, auditing, and unified account history.

**Improvement**
- Introduce a primary `User` identity (one row per mobile), then model role assignments via many-to-many (`UserRole`) or related profile tables.

### 2) Mobile stored as plain `CharField` without model-level validation
**Status: Valid issue (still present at model layer).**

- `UserRegistration.mobile` is `models.CharField(max_length=10)` without validators.
- View-level checks (`is_valid_mobile`) exist, but model saves outside those views can still persist invalid values (admin, shell, fixtures, custom scripts).

**Improvement**
- Add `RegexValidator` on model field.
- Add DB-level constraint where possible (check constraint for numeric/length pattern).
- Reuse one central validator across model/forms/services.

### 3) Custom `UserRegistration` model instead of Django auth user model
**Status: Valid architectural gap.**

- The project uses `UserRegistration` and manual session flags (`user_id`, `otp_verified`, `role`) rather than `AUTH_USER_MODEL`.
- This bypasses first-class Django auth workflows (permissions backend, password policies by default auth, admin user ops, pluggable auth apps).

**Improvement**
- Migrate to custom user extending `AbstractUser` (or `AbstractBaseUser` if mobile-first username).
- Move OTP login into custom authentication backend.
- Use Django permission/groups directly on authenticated users instead of ad-hoc session role handling.

### 4) Missing `requirements.txt`
**Status: Not currently true.**

- `requirements.txt` exists.

**But there is still improvement needed:**
- Dependencies are unpinned (`django`, `requests`, etc.), which harms reproducibility.

**Improvement**
- Pin versions (`Django==x.y.z` etc.).
- Optionally split to `requirements/base.txt`, `dev.txt`, `prod.txt`.

### 5) Missing `README.md`
**Status: Not currently true, but documentation quality is broken.**

- `README.md` exists, but appears corrupted: setup content is followed by unrelated template/CSS content.

**Impact**
- New developers may be confused and miss critical setup/deployment steps.

**Improvement**
- Rewrite README with:
  - project overview
  - prerequisites and env vars
  - install/migrate/run/test commands
  - OTP flow notes
  - production deployment checklist

### 6) OTP security gaps (expiration and attempt limits)
**Status: Mostly addressed, still hardening opportunities remain.**

Implemented:
- OTP TTL (`OTP_TTL_SECONDS`) in payload with expiration check.
- Rate limiting via cache (`OTP_REQUEST_LIMIT`, `OTP_REQUEST_WINDOW_SECONDS`).
- Login and registration invalid OTP attempt caps (`>= 5`) in session.

Remaining gaps:
- OTP stored in plain session payload (not hashed).
- No per-OTP replay/jti tracking beyond session lifecycle.
- Brute-force control is mostly mobile/session scoped; device/IP telemetry is limited.

**Improvement**
- Store hashed OTP + metadata server-side (cache/DB), compare constant-time.
- Add stronger lockout strategy (mobile + IP + device fingerprint where possible).
- Add audit trail for OTP issue/verify failures.

### 7) Hardcoded config values
**Status: Partially true.**

- Many settings are env-driven (good).
- However `settings.py` has duplicated DB config blocks and repeated `CSRF_TRUSTED_ORIGINS` assignment, which increases misconfiguration risk.
- Some default values remain hardcoded and should be consolidated/validated centrally.

**Improvement**
- Remove duplicate DB declarations.
- Keep single source of truth per setting.
- Add startup checks (`django check --deploy`) and custom system checks.

### 8) No REST APIs for mobile integration
**Status: Mostly true.**

- There are JSON utility endpoints (`get-location`, villages), but no formal REST resource layer.
- No DRF serializers/viewsets/auth tokens/versioned API namespace.

**Improvement**
- Add Django REST Framework.
- Build `/api/v1/...` endpoints for registration/login-OTP, profile, provider discovery, bookings, order tracking.
- Add token-based auth (JWT or DRF token), throttling, and API schema (OpenAPI).

### 9) Missing robust error handling in views
**Status: Improved but still inconsistent.**

- Global exception middleware exists and returns safe JSON for API/ajax paths.
- Some views still rely on manual parsing from `request.POST` without form validation/typed cleaning.

**Improvement**
- Move all write flows to Django Forms/ModelForms or DRF serializers.
- Use explicit validation/error responses for bad input; avoid implicit failures.
- Add domain exceptions with predictable handling.

### 10) Missing DB optimization/indexing on frequently queried fields
**Status: Largely addressed, but can be improved further.**

- Indexes exist for key query paths (`mobile+role`, `role`, status/date combinations, pincode).
- Remaining opportunities:
  - evaluate composite indexes based on actual query plans (`EXPLAIN ANALYZE`)
  - add uniqueness/constraints for data integrity where business rules demand it
  - reduce text-heavy denormalized fields used for filtering/search

---

## Additional Security Recommendations
- Migrate from session-only pseudo-auth to Django auth + secure OTP backend.
- Add CSRF and session hardening verification under production proxy/HTTPS.
- Add admin hardening: MFA for admin, restricted staff accounts, audit logging.
- Add SAST/dependency scanning in CI (`pip-audit`, bandit).
- Ensure PII handling policy for mobile/location data (retention + masking).

## Scalability Recommendations
- Replace local memory cache with Redis for OTP/rate-limiting in multi-instance deployments.
- Introduce async tasks (Celery/RQ) for SMS sending and heavy imports.
- Add DB connection pooling and pagination for provider listings/bookings.
- Normalize product/services metadata now stored in text blobs for better querying.

## Project Structure Recommendations
- Keep current split view modules and continue: `auth`, `booking`, `location`, `dashboard`, `api`.
- Introduce service layer for booking orchestration and pricing logic.
- Add DTO/serializer or form layer uniformly (avoid direct `request.POST` parsing in views).
- Establish tests by module: unit, integration, and auth/OTP regression tests.

## Production Readiness Checklist (Suggested)
1. Adopt custom `AUTH_USER_MODEL` with mobile-based login.
2. Introduce DRF API v1 with token auth + throttling.
3. Move cache to Redis and externalize all secrets.
4. Pin and lock dependencies.
5. Fix README and add `.env.example` completeness.
6. Add CI pipeline: lint, test, security scan, migration check.
7. Add observability: structured logs, error monitoring (Sentry), health checks.
