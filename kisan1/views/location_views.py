from django.http import JsonResponse

from kisan1.location_service import get_cached_location_details, load_telangana_pincodes
from kisan1.models import PincodeMapping


def get_villages_by_pincode(request):
    pincode = request.GET.get('pincode')
    if not pincode:
        return JsonResponse({'villages': []})

    villages = list(
        PincodeMapping.objects.filter(pincode=pincode).values_list('village', flat=True).distinct()
    )
    return JsonResponse({'villages': villages})


def get_location_api(request):
    pincode_input = request.GET.get('pincode', '')

    if len(pincode_input) == 6 and pincode_input.isdigit():
        # Load pincodes into DB if it is completely empty
        if not PincodeMapping.objects.exists():
            try:
                load_telangana_pincodes(force=False)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Location data unavailable'}, status=503)

        location_data = get_cached_location_details(pincode_input)
        if location_data:
            return JsonResponse({
                'success': True,
                'district': location_data['district'],
                'mandal': location_data['mandal'],
                'villages': location_data['villages'],
            })

    return JsonResponse({'success': False})
