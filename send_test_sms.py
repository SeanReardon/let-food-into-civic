#!/usr/bin/env python3
"""
Send "hello world" test SMS to all NOTIFY_NUMBERS from the 214 number.
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

load_dotenv()

api_key = os.getenv("TELNYX_LET_FOOD_INTO_CIVIC_KEY")
from_number = os.getenv("TELNYX_PHONE_NUMBER")
notify_numbers = [n.strip() for n in os.getenv("NOTIFY_NUMBERS", "").split(",") if n.strip()]

print("📱 Sending Test SMS")
print("=" * 50)
print(f"From: {from_number}")
print(f"To: {notify_numbers}")
print("=" * 50)

if not api_key:
    print("❌ TELNYX_LET_FOOD_INTO_CIVIC_KEY not set")
    exit(1)

if not from_number:
    print("❌ TELNYX_PHONE_NUMBER not set")
    exit(1)

if not notify_numbers:
    print("❌ NOTIFY_NUMBERS not set")
    exit(1)

client = telnyx.Telnyx(api_key=api_key)

for phone in notify_numbers:
    print(f"\n📤 Sending to {phone}...")
    try:
        client.messages.send(
            from_=from_number,
            to=phone,
            text="hello world",
        )
        print(f"   ✅ Sent!")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

print("\n" + "=" * 50)
print("✅ Done! Check your phones.")

