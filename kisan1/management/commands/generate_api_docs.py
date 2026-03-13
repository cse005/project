from pathlib import Path

from django.core.management.base import BaseCommand
from django.urls import URLPattern, URLResolver, get_resolver


class Command(BaseCommand):
    help = 'Generate API/endpoint markdown docs from Django URL patterns'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='API_DOCUMENTATION.md', help='Output markdown path')

    def _flatten(self, patterns, prefix=''):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from self._flatten(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                route = prefix + str(pattern.pattern)
                yield route, pattern.name or 'unnamed'

    def handle(self, *args, **options):
        output = Path(options['output'])
        resolver = get_resolver()
        rows = sorted(set(self._flatten(resolver.url_patterns)), key=lambda x: x[0])

        lines = [
            '# API Documentation (Auto-generated)',
            '',
            'This file is generated via `python manage.py generate_api_docs`.',
            '',
            '| Route | Name |',
            '|---|---|',
        ]
        lines.extend([f'| `/{route}` | `{name}` |' for route, name in rows])
        lines.append('')

        output.write_text('\n'.join(lines), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Generated endpoint docs at {output}'))
