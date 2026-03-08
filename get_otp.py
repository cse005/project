import argparse
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farmer_project.settings')
django.setup()

from kisan1.views.shared import create_otp_session_payload  # noqa: E402


parser = argparse.ArgumentParser(description='Generate TOTP for local debugging.')
parser.add_argument('--show-otp', action='store_true', help='Print OTP value to stdout (unsafe for shared terminals).')
args = parser.parse_args()

if args.show_otp:
    print(f"Current OTP: {totp.now()}")
else:
    print('OTP generated. Pass --show-otp to display it explicitly.')

payload = create_otp_session_payload()
if args.show_otp:
    print(f"Current OTP: {payload['code']}")
else:
    print('OTP payload generated. Pass --show-otp to display the code explicitly.')
print(f"Expires At: {payload['expires_at']}")
