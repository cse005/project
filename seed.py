from kisan1.models import PincodeMapping
from kisan1.pincode_data import PINCODE_DATA
from django.core.exceptions import ValidationError

print("Starting to load pincodes...")

for pin, data in PINCODE_DATA.items():
    villages_string = ", ".join(data['villages'])
    try:
        PincodeMapping.objects.get_or_create(
            pincode=pin,
            defaults={
                'district': data['district'],
                'mandal': data['mandal'],
                'village': villages_string, 
                'state': 'Telangana'
            }
        )
        print(f"✅ Saved {pin}")
    except ValidationError:
        print(f"⚠️ Skipped {pin}: Restricted Pincode")

print("🎉 SUCCESS: All data loaded!")