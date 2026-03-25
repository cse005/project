from kisan1.models import PincodeMapping
from kisan1.pincode_data import PINCODE_DATA, is_hidden_pincode

def run():
    count = 0
    skipped = 0

    for pincode, details in PINCODE_DATA.items():

        # 🔥 SKIP restricted pincodes
        if is_hidden_pincode(str(pincode)):
            print(f"⛔ Skipping restricted pincode: {pincode}")
            skipped += 1
            continue

        district = details.get("district")
        mandal = details.get("mandal")
        villages = details.get("villages", [])

        for village in villages:
            obj, created = PincodeMapping.objects.get_or_create(
                pincode=str(pincode),
                district=district,
                mandal=mandal,
                village=village
            )

            if created:
                count += 1

    print(f"✅ Loaded {count} records")
    print(f"⛔ Skipped {skipped} restricted pincodes")