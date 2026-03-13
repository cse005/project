import logging

from django.core.cache import cache
from django.db import transaction

from kisan1.models import PincodeMapping
from kisan1.pincode_data import PINCODE_DATA

logger = logging.getLogger(__name__)


def load_telangana_pincodes(force=False):
    """Load bundled Telangana pincode/mandal/village data into DB."""
    if not force and PincodeMapping.objects.exists():
        return 0

    if force:
        PincodeMapping.objects.all().delete()

    created_count = 0
    with transaction.atomic():
        for pincode, data in PINCODE_DATA.items():
            district = data['district']
            mandal = data['mandal']
            for village in data['villages']:
                _, created = PincodeMapping.objects.get_or_create(
                    pincode=pincode,
                    district=district,
                    mandal=mandal,
                    village=village,
                )
                if created:
                    created_count += 1
    return created_count


def get_cached_location_details(pincode):
    cache_key = f'location:pincode:{pincode}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    locations = PincodeMapping.objects.filter(pincode=pincode)
    if not locations.exists():
        logger.info('No location mapping found for pincode=%s', pincode)
        cache.set(cache_key, None, 60)
        return None

    first_record = locations.first()
    villages_by_mandal = {}
    for row in locations.values('mandal', 'village').order_by('mandal', 'village'):
        mandal = row['mandal']
        village = row['village']
        villages_by_mandal.setdefault(mandal, [])
        if village not in villages_by_mandal[mandal]:
            villages_by_mandal[mandal].append(village)

    mandals = list(villages_by_mandal.keys())
    default_mandal = first_record.mandal if first_record.mandal in villages_by_mandal else mandals[0]
    data = {
        'district': first_record.district,
        'mandal': default_mandal,
        'mandals': mandals,
        'villages': villages_by_mandal.get(default_mandal, []),
        'villages_by_mandal': villages_by_mandal,
    }
    cache.set(cache_key, data, 600)
    return data
