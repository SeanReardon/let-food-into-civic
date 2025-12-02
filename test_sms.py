#!/usr/bin/env python3
"""
Quick test script to verify Telnyx SMS is working.
Sends a test message to all numbers in NOTIFY_NUMBERS.
"""

import os
from dotenv import load_dotenv
import telnyx

# Load environment variables
load_dotenv()

# Get config
api_key = os.getenv("TELNYX_LET_FOOD_INTO_CIVIC_KEY")
from_number = os.getenv("TELNYX_PHONE_NUMBER")
notify_numbers = [n.strip() for n in os.getenv("NOTIFY_NUMBERS", "").split(",") if n.strip()]

print("🧪 Telnyx SMS Test")
print("=" * 40)

# Check configuration
if not api_key:
    print("❌ TELNYX_LET_FOOD_INTO_CIVIC_KEY not set in .env")
    exit(1)
else:
    print(f"✅ API Key: {api_key[:10]}...")

if not from_number:
    print("❌ TELNYX_PHONE_NUMBER not set in .env")
    exit(1)
else:
    print(f"✅ From Number: {from_number}")

if not notify_numbers:
    print("❌ NOTIFY_NUMBERS not set in .env")
    exit(1)
else:
    print(f"✅ Notify Numbers: {notify_numbers}")

print("=" * 40)

# Initialize Telnyx client
client = telnyx.Telnyx(api_key=api_key)

# Send test messages
for phone in notify_numbers:
    print(f"\n📱 Sending to {phone}...")
    try:
        message = client.messages.send(
            from_=from_number,
            to=phone,
            text="👋 Hello from let-food-into-civic! Your SMS notifications are working. 🍕",
        )
        print(f"   ✅ Sent!")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

print("\n" + "=" * 40)
print("Done! Check your phones. 📱")
