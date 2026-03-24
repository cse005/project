from django.apps import AppConfig
from django.db.models.signals import post_migrate


class Kisan1Config(AppConfig):
    name = 'kisan1'

    def ready(self):
        from django.db.utils import OperationalError, ProgrammingError
        from kisan1.location_service import load_telangana_pincodes
        from kisan1.models import PincodeMapping

        def _ensure_pincodes(**kwargs):
            try:
                if not PincodeMapping.objects.exists():
                    load_telangana_pincodes(force=False)
            except (OperationalError, ProgrammingError):
                return

        post_migrate.connect(_ensure_pincodes, sender=self, dispatch_uid='kisan1_load_pincodes')
