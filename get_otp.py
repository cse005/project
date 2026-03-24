import argparse
import os
import requests
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farmer_project.settings')
django.setup()

from kisan1.views.shared import create_otp_session_payload

# Argument parser
parser = argparse.ArgumentParser(description='Generate OTP and send SMS')
parser.add_argument('--show-otp', action='store_true')
parser.add_argument('--phone', type=str, help='Enter phone number')
args = parser.parse_args()

# Get phone number
phone = args.phone

if not phone:
    phone = input("Enter phone number: ")

# Generate OTP
payload = create_otp_session_payload()
otp = payload['code']

# Show OTP (optional)
if args.show_otp:
    print(f"OTP: {otp}")

print(f"Expires At: {payload['expires_at']}")
print("Sending OTP to:", phone)

# Get API key
API_KEY = os.getenv("FAST2SMS_API_KEY")

# Function to send OTP
def send_otp(phone, otp):
    url = "https://www.fast2sms.com/dev/bulkV2"

    payload = {
        "authorization": API_KEY,
        "sender_id": "FSTSMS",
        "message": f"Your OTP is {otp}",
        "language": "english",
        "route": "q",
        "numbers": phone
    }

    headers = {
        "cache-control": "no-cache"
    }

    response = requests.post(url, data=payload, headers=headers)
    print("SMS Response:", response.text)

# CALL FUNCTION (VERY IMPORTANT)
send_otp(phone, otp)