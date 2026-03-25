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
    if not User.objects.filter(username="admin").exists():
        user = User.objects.create_user(
            username="admin",
            email="test@gmail.com",
            password="123456"
        )
        print("User created")
    else:
        user = User.objects.get(username="admin")
        print("User already exists")

    # ALWAYS update permissions
    user.is_staff = True
    user.is_superuser = True
    user.set_password("123456")  # ensure password works
    user.save()

    print("Admin access granted")