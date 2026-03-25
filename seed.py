import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farmer_project.settings')
django.setup()




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
from django.contrib.auth.models import User

def run():
    if not User.objects.filter(username="testuser").exists():
        User.objects.create_user(
            username="testuser",
            email="test@gmail.com",
            password="123456"
        )
        print("Test user created")
    else:
        print("User already exists")