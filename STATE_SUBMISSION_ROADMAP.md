# State-Level Submission Roadmap

This document captures implementation status and architecture for advanced requirements.

## ✅ Implemented in codebase now
- Session inactivity timeout and role-bound session (`SessionSecurityMiddleware`).
- Self-booking prevention across service flows.
- Environment-driven secret/security config.
- OTP attempt throttling (session-based lock after repeated failures).
- Role-group provisioning with Django Groups.
- Admin analytics dashboard with revenue/status/service charts.
- Telangana pincode/mandal/village offline data loader + APIs.

## 🚧 Next modules (scaffold plan)
1. RBAC hardening
   - Move all role checks to `@role_required` decorators + per-view permission matrix.
   - Add model-level permissions and group sync command.

2. Payment integration (Razorpay/Stripe)
   - Add `PaymentTransaction` model.
   - states: `initiated/authorized/captured/refunded/failed`.

3. Notifications (SMS + WhatsApp)
   - Provider abstraction: `NotificationService`.
   - Template-based notifications per booking event.

4. Celery + Redis
   - async OTP send
   - reminder jobs
   - inventory low-stock scheduled job

5. Search + filtering + pagination
   - district/price/skill filters in listing endpoints
   - sorting + server-side pagination everywhere

6. REST API + mobile readiness
   - DRF + JWT
   - `/api/v1/` versioned routes
   - Flutter/React client compatibility

7. Ratings/reviews
   - `Review` model and aggregate score per provider.

8. Inventory alerts
   - low-stock threshold config
   - email/SMS alerts and stock freeze at zero.

9. Smart agriculture modules
   - weather API aggregation
   - crop recommendation rule engine
   - seasonal planner and risk score.

10. Security hardening for production
    - OTP/IP rate limiting (cache-backed)
    - account lockout persistence
    - audit logs + suspicious activity flags
    - secret rotation policy

## Suggested sequence
Phase 1: RBAC + payment + notification + Celery
Phase 2: REST API + search/filter + reviews
Phase 3: weather/crop/risk analytics and geo services
