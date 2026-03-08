import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class PasswordComplexityValidator:
    def validate(self, password, user=None):
        checks = [
            (r'[A-Z]', 'at least one uppercase letter'),
            (r'[a-z]', 'at least one lowercase letter'),
            (r'[0-9]', 'at least one digit'),
            (r'[^A-Za-z0-9]', 'at least one special character'),
        ]
        missing = [message for pattern, message in checks if not re.search(pattern, password or '')]
        if missing:
            raise ValidationError(
                _('Password must contain %(rules)s.'),
                code='password_no_complexity',
                params={'rules': ', '.join(missing)},
            )

    def get_help_text(self):
        return _('Your password must include uppercase, lowercase, numeric, and special characters.')
