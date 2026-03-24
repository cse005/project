from django.http import JsonResponse
from kisan1.models import PincodeMapping
from kisan1.pincode_data import is_hidden_pincode

def get_villages_by_pincode(request):
    pincode = request.GET.get('pincode')
    
    # 1. Security Check
    if not pincode or is_hidden_pincode(pincode):
        return JsonResponse({'villages': []})

    try:
        # 2. Grab from Database
        mapping = PincodeMapping.objects.get(pincode=pincode)
        
        # 3. Convert the comma-separated string back into a clean list
        villages_list = [v.strip() for v in mapping.village.split(',')] if mapping.village else []
        return JsonResponse({'villages': villages_list})
        
    except PincodeMapping.DoesNotExist:
        return JsonResponse({'villages': []})


def get_location_api(request):
    pincode_input = request.GET.get('pincode', '')

    # 1. Validate Input
    if len(pincode_input) == 6 and pincode_input.isdigit():
        
        # 2. Security Check
        if is_hidden_pincode(pincode_input):
            return JsonResponse({'success': False, 'error': 'Restricted Pincode'})
        
        # 3. Grab the FIRST matching record from Database (This fixes the crash!)
        location = PincodeMapping.objects.filter(pincode=pincode_input).first()
        
        if location:
            # Convert the comma-separated string back into a list
            villages_list = [v.strip() for v in location.village.split(',')] if location.village else []

            # 4. Send exactly what the frontend needs
            return JsonResponse({
                'success': True,
                'district': location.district,
                'mandal': location.mandal,
                'villages': villages_list,
            })
        else:
            return JsonResponse({'success': False, 'error': 'Pincode not found'})

    return JsonResponse({'success': False, 'error': 'Invalid Pincode'})