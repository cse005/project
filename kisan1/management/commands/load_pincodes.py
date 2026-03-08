from django.core.management.base import BaseCommand

from kisan1.location_service import load_telangana_pincodes


class Command(BaseCommand):
    help = 'Loads bundled Telangana pincode and village data into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete existing pincode mappings and reload from bundled data',
        )

    def handle(self, *args, **options):
        try:
            created = load_telangana_pincodes(force=options['force'])
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Failed to load pincode mappings: {exc}'))
            raise
        self.stdout.write(self.style.SUCCESS(f'Successfully saved {created} new villages to the database!'))
