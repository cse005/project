from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from kisan1.models import UserRegistration


def session_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not (request.session.get('user_id') and request.session.get('otp_verified')):
            messages.error(request, 'Please login to continue.')
            return redirect('login')
        return view_func(request, *args, **kwargs)

    return _wrapped


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            active_role = request.session.get('active_role') or request.session.get('role')

            # Backward-compatible fallback for older sessions/tests that only store user_id.
            if not active_role and request.session.get('user_id'):
                user = UserRegistration.objects.filter(id=request.session['user_id']).only('role').first()
                if user:
                    active_role = user.role
                    request.session['role'] = user.role
                    request.session['active_role'] = user.role

            if active_role not in allowed_roles:
                messages.error(request, 'You do not have permission to access this action.')
                return redirect('login')
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
