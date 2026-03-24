import logging
import os
import re
import secrets
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from kisan1.models import UserRegistration

DEBUG_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
logger = logging.getLogger(__name__)
NAME_RE = re.compile(r'^[A-Za-z\s]{3,80}$')
MOBILE_RE = re.compile(r'^[6-9][0-9]{9}$')


def is_debug_mode():
    return os.getenv('DJANGO_DEBUG', 'false').strip().lower() in DEBUG_TRUE_VALUES


def check_login(request):
    return bool(request.session.get('user_id') and request.session.get('otp_verified'))


def get_logged_in_user(request):
    user_id = request.session.get('user_id')
    return get_object_or_404(UserRegistration, id=user_id)


def is_valid_name(value):
    return bool(value and NAME_RE.fullmatch(value.strip()))


def is_valid_mobile(value):
    return bool(value and MOBILE_RE.fullmatch(value.strip()))


def otp_rate_limit_key(mobile, context='generic'):
    return f'otp_rate_limit:{context}:{mobile}'


def login_attempt_limit_key(mobile, context='login_attempts'):
    return f'auth_login_attempts:{context}:{mobile}'


def can_send_otp(mobile, context='generic'):
    key = otp_rate_limit_key(mobile, context)
    attempts = cache.get(key, 0)
    limit = getattr(settings, 'OTP_REQUEST_LIMIT', 5)
    window = getattr(settings, 'OTP_REQUEST_WINDOW_SECONDS', 300)

    if attempts >= limit:
        return False
    cache.set(key, attempts + 1, timeout=window)
    return True


def can_attempt_login(mobile, context='generic'):
    key = login_attempt_limit_key(mobile, context)
    attempts = cache.get(key, 0)
    limit = getattr(settings, 'LOGIN_ATTEMPT_LIMIT', 5)
    return attempts < limit


def register_failed_login_attempt(mobile, context='generic'):
    key = login_attempt_limit_key(mobile, context)
    attempts = cache.get(key, 0)
    window = getattr(settings, 'LOGIN_ATTEMPT_WINDOW_SECONDS', 300)
    cache.set(key, attempts + 1, timeout=window)


def clear_login_attempts(mobile, context='generic'):
    cache.delete(login_attempt_limit_key(mobile, context))


def _hash_otp_code(code):
    return salted_hmac('kisan1.otp', str(code).strip()).hexdigest()


def create_otp_session_payload():
    otp = f"{secrets.randbelow(9000) + 1000}"
    expires_at = (timezone.now() + timedelta(minutes=5)).isoformat()
    return otp, {'code_hash': _hash_otp_code(otp), 'expires_at': expires_at}


def get_otp_remaining_seconds(payload):
    if not payload or isinstance(payload, str):
        return None

    if isinstance(payload, tuple) and len(payload) == 2:
        payload = payload[1]

    expires_at = payload.get('expires_at')
    if not expires_at:
        return None

    try:
        expires_at_dt = datetime.fromisoformat(expires_at)
    except ValueError:
        return None

    if timezone.is_naive(expires_at_dt):
        expires_at_dt = timezone.make_aware(expires_at_dt, timezone.get_current_timezone())

    remaining = int((expires_at_dt - timezone.now()).total_seconds())
    return max(0, remaining)


def is_otp_expired(payload):
    remaining = get_otp_remaining_seconds(payload)
    if remaining is None:
        return False
    return remaining <= 0


def is_otp_valid(payload, provided_otp):
    if not payload or not provided_otp:
        return False

    if isinstance(payload, tuple) and len(payload) == 2:
        payload = payload[1]

    provided = str(provided_otp).strip()

    if isinstance(payload, str):
        return constant_time_compare(payload, provided)

    expires_at = payload.get('expires_at')
    if not expires_at:
        return False

    expires_at_dt = datetime.fromisoformat(expires_at)
    if timezone.is_naive(expires_at_dt):
        expires_at_dt = timezone.make_aware(expires_at_dt, timezone.get_current_timezone())

    if timezone.now() > expires_at_dt:
        return False

    code_hash = payload.get('code_hash')
    if not code_hash:
        legacy_code = payload.get('code')
        return bool(legacy_code and constant_time_compare(str(legacy_code), provided))

    return constant_time_compare(code_hash, _hash_otp_code(provided))


def announce_otp(mobile, otp, context='generic'):
    logger.info('%s OTP generated for %s', context.upper(), mobile)
    if getattr(settings, 'OTP_PRINT_TO_TERMINAL', False):
        print(f"[OTP][{context}] mobile={mobile} code={otp}")


def send_real_otp_sms(mobile, otp):
    api_token = os.getenv('FAST2SMS_API_KEY')

    if not api_token:
     logger.warning('FAST2SMS_API_KEY not configured. OTP SMS skipped.')
     return False

    url = "https://www.fast2sms.com/dev/bulkV2"
    querystring = {
        "authorization": api_token,
        "message": f"Your Kisan Asara test OTP is {otp}",
        "language": "english",
        "route": "q",
        "numbers": mobile,
    }
    headers = {'cache-control': "no-cache"}

    try:
        response = requests.request("GET", url, headers=headers, params=querystring, timeout=10)
        logger.info('SMS API Response: %s', response.text)
        return True
    except requests.RequestException as exc:
        logger.exception('Error sending SMS: %s', exc)
        return False
import requests
import os

