#!/usr/bin/env python3
"""
Set up Telnyx messaging profile and assign phone number to it.
Run this after buying a new phone number to enable SMS.
"""

import os
from dotenv import load_dotenv
import telnyx

load_dotenv()

api_key = os.getenv("LET-FOOD-INTO-CIVIC-KEY")
phone_number = os.getenv("TELNYX_PHONE_NUMBER")

if not api_key:
    print("❌ LET-FOOD-INTO-CIVIC-KEY not set")
    exit(1)

if not phone_number:
    print("❌ TELNYX_PHONE_NUMBER not set")
    exit(1)

client = telnyx.Telnyx(api_key=api_key)

print("🔧 Setting up Telnyx Messaging")
print("=" * 50)

# Step 1: Create or find a messaging profile
print("\n1️⃣  Setting up messaging profile...")
profile_id = None

try:
    # First, check if we already have a profile
    profiles = client.messaging_profiles.list()
    for p in profiles.data:
        if p.name == "let-food-into-civic":
            profile_id = p.id
            print(f"   ✅ Found existing profile: {profile_id}")
            break
    
    # If not, create one
    if not profile_id:
        print("   Creating new profile...")
        profile = client.messaging_profiles.create(
            name="let-food-into-civic",
            whitelisted_destinations=["US"]  # Required field
        )
        profile_id = profile.data.id
        print(f"   ✅ Created profile: {profile_id}")

except Exception as e:
    print(f"   ❌ Error with messaging profile: {e}")
    exit(1)

# Step 2: Get the phone number ID
print(f"\n2️⃣  Finding phone number {phone_number}...")
try:
    numbers = client.phone_numbers.list(
        filter={"phone_number": phone_number}
    )
    if not numbers.data:
        print(f"   ❌ Phone number {phone_number} not found in your account")
        exit(1)
    
    number_id = numbers.data[0].id
    print(f"   ✅ Found number ID: {number_id}")
except Exception as e:
    print(f"   ❌ Error finding number: {e}")
    exit(1)

# Step 3: Assign the messaging profile to the phone number
print(f"\n3️⃣  Assigning messaging profile to phone number...")
try:
    result = client.phone_numbers.messaging.update(
        id=number_id,
        messaging_profile_id=profile_id
    )
    print(f"   ✅ Messaging profile assigned!")
    print(f"   Messaging Profile ID: {result.data.messaging_profile_id}")
except Exception as e:
    print(f"   ❌ Error assigning profile: {e}")
    exit(1)

print("\n" + "=" * 50)
print("✅ Messaging setup complete!")
print(f"   Profile ID: {profile_id}")
print(f"   Phone Number: {phone_number}")
print("\nNow run: python test_sms.py")
