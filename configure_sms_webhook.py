#!/usr/bin/env python3
"""
Configure SMS webhook URL in Telnyx messaging profile.
"""

import os
import sys
# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from dotenv import load_dotenv
import telnyx
import httpx

load_dotenv()

api_key = os.getenv("TELNYX_LET_FOOD_INTO_CIVIC_KEY")
phone_number = os.getenv("TELNYX_PHONE_NUMBER")

if not api_key:
    print("❌ TELNYX_LET_FOOD_INTO_CIVIC_KEY not set")
    exit(1)

if not phone_number:
    print("❌ TELNYX_PHONE_NUMBER not set")
    exit(1)

# Normalize phone number
def normalize_phone(phone: str) -> str:
    import re
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return '+1' + digits
    elif len(digits) == 11 and digits.startswith('1'):
        return '+' + digits
    return phone

phone_number = normalize_phone(phone_number)

# Webhook URL - update this to your actual domain
webhook_url = "https://let-food-into-civic.contrived.com/webhook/sms"

print("🔧 Configuring SMS Webhook in Telnyx")
print("=" * 60)
print(f"Phone Number: {phone_number}")
print(f"Webhook URL: {webhook_url}")
print("=" * 60)

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

try:
    # Step 1: Get the phone number details to find its messaging profile
    print("\n1️⃣  Finding phone number and messaging profile...")
    response = httpx.get(
        f"https://api.telnyx.com/v2/phone_numbers",
        headers=headers,
        params={"filter[phone_number]": phone_number}
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to get phone number: {response.status_code}")
        print(response.text)
        exit(1)
    
    data = response.json()
    phone_numbers = data.get('data', [])
    
    if not phone_numbers:
        print(f"❌ Phone number {phone_number} not found in your account")
        exit(1)
    
    phone_number_data = phone_numbers[0]
    messaging_profile_id = phone_number_data.get('messaging_profile_id')
    
    if not messaging_profile_id:
        print(f"❌ Phone number {phone_number} is not assigned to a messaging profile")
        print("   You may need to assign it to a messaging profile first")
        exit(1)
    
    print(f"   ✅ Found messaging profile: {messaging_profile_id}")
    
    # Step 2: Get the messaging profile details
    print("\n2️⃣  Getting messaging profile details...")
    profile_response = httpx.get(
        f"https://api.telnyx.com/v2/messaging_profiles/{messaging_profile_id}",
        headers=headers
    )
    
    if profile_response.status_code != 200:
        print(f"❌ Failed to get messaging profile: {profile_response.status_code}")
        print(profile_response.text)
        exit(1)
    
    profile_data = profile_response.json().get('data', {})
    print(f"   ✅ Profile name: {profile_data.get('name', 'N/A')}")
    
    # Step 3: Update the messaging profile with webhook URL
    print("\n3️⃣  Updating messaging profile with webhook URL...")
    update_data = {
        "webhook_url": webhook_url,
        "webhook_failover_url": "",
        "webhook_api_version": "2"
    }
    
    update_response = httpx.patch(
        f"https://api.telnyx.com/v2/messaging_profiles/{messaging_profile_id}",
        headers=headers,
        json=update_data
    )
    
    if update_response.status_code == 200:
        updated_profile = update_response.json().get('data', {})
        print(f"   ✅ Successfully updated messaging profile!")
        print(f"   Webhook URL: {updated_profile.get('webhook_url', 'N/A')}")
        print(f"   Webhook API Version: {updated_profile.get('webhook_api_version', 'N/A')}")
        print("\n🎉 SMS webhook configured! Try texting 'HELP' to your number.")
    else:
        print(f"❌ Failed to update messaging profile: {update_response.status_code}")
        print(update_response.text)
        exit(1)

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

