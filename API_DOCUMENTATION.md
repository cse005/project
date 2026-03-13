# API & Endpoint Notes

## Auth and Session

- `POST /login/`: Initiates OTP login for registered users.
- `POST /verify-otp-login/`: Verifies OTP, enforces OTP expiry and login-attempt throttling.
- `POST /verify-otp/`: Verifies OTP during registration.

## Location APIs

- `GET /get-villages/?pincode=<6_digits>`
  - Returns a villages array for matching pincode.
- `GET /get-location/?pincode=<6_digits>`
  - Returns:
    - `success: true`
    - `district`
    - `mandal`
    - `villages`
  - Returns `success: false` when no mapping exists.

## Booking APIs (HTML endpoints)

- `POST /book-labor/<labor_id>/`
- `POST /book-tractor/<tractor_id>/`
- `POST /book-tool/<tool_id>/`
- `POST /request-lease/<land_id>/`
- `POST /book-shop/<shop_id>/`

These endpoints enforce session login + role checks and create normalized `Order` records for analytics.

## Versioning Guidance

Current endpoints are server-rendered and unversioned. If external/mobile clients are introduced, adopt `/api/v1/...` namespace and schema contracts.
