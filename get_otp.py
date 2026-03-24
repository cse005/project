import argparse
import os
import django
import requests

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farmer_project.settings')
django.setup()

from kisan1.views.shared import create_otp_session_payload

# Argument parser
parser = argparse.ArgumentParser(description='Generate OTP and send SMS')
parser.add_argument('--show-otp', action='store_true')
parser.add_argument('--phone', type=str, help='Enter phone number')
args = parser.parse_args()

# STEP 1: Get phone number
phone = args.phone
if not phone:
    phone = input("Enter phone number: ")

# STEP 2: Generate OTP
payload = create_otp_session_payload(phone)
otp = payload['code']

# STEP 3: Print info
if args.show_otp:
    print(f"OTP: {otp}")

print(f"Expires At: {payload['expires_at']}")
print("Sending OTP to:", phone)

# STEP 4: Get API key
API_KEY = os.getenv("FAST2SMS_API_KEY")

# STEP 5: Send OTP function
def send_otp(phone, otp):
    url = "https://www.fast2sms.com/dev/bulkV2"

    headers = {
        "authorization": API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "sender_id": "FSTSMS",   # REQUIRED
        "message": f"Your OTP is {otp}",
        "language": "english",
        "route": "q",            # keep q for now
        "numbers": phone
    }

    response = requests.post(url, data=data, headers=headers)

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

# STEP 6: CALL FUNCTION
send_otp(phone, otp)
