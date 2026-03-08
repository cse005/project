from datetime import timedelta
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger(__name__)


class SessionSecurityMiddleware:
    """Expire inactive sessions and keep a single active role bound to session."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session.get('user_id') and request.session.get('otp_verified'):
            now = timezone.now()
            last_seen_str = request.session.get('last_seen_at')
            timeout_seconds = int(getattr(settings, 'SESSION_COOKIE_AGE', 1200))

            if last_seen_str:
                last_seen = timezone.datetime.fromisoformat(last_seen_str)
                if timezone.is_naive(last_seen):
                    last_seen = timezone.make_aware(last_seen, timezone.get_current_timezone())
                if now - last_seen > timedelta(seconds=timeout_seconds):
                    request.session.flush()
                    return redirect('login')

            request.session['last_seen_at'] = now.isoformat()

            # Bind access to one role per login session
            active_role = request.session.get('active_role')
            role = request.session.get('role')
            if active_role and role and active_role != role:
                request.session.flush()
                return redirect('login')

        return self.get_response(request)


class RequestAuditMiddleware:
    """Minimal structured request logging for debugging and audits."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = timezone.now()
        response = self.get_response(request)
        elapsed_ms = (timezone.now() - started_at).total_seconds() * 1000
        logger.info(
            'request_completed method=%s path=%s status=%s duration_ms=%.2f user_id=%s',
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
            request.session.get('user_id'),
        )
        return response


class GlobalExceptionMiddleware:
    """Capture uncaught exceptions and return safe API errors for JSON clients."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            logger.exception('unhandled_exception path=%s method=%s', request.path, request.method)
            if request.path.startswith('/api/') or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Internal server error.'}, status=500)
            raise
