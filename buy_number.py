#!/usr/bin/env python3
"""
Search for and purchase a phone number from Telnyx.
"""

import os
from dotenv import load_dotenv
import telnyx

load_dotenv()

api_key = os.getenv("LET-FOOD-INTO-CIVIC-KEY")
if not api_key:
    print("❌ LET-FOOD-INTO-CIVIC-KEY not set")
    exit(1)

# Create client with API key
client = telnyx.Telnyx(api_key=api_key)

AREA_CODE = "214"  # Dallas area

print(f"🔍 Searching for available numbers in area code {AREA_CODE}...")
print("=" * 50)

try:
    # Search for available numbers
    response = client.available_phone_numbers.list(
        filter={
            "country_code": "US",
            "national_destination_code": AREA_CODE,
            "limit": 5,
        }
    )
    
    numbers = response.data
    
    if not numbers:
        print("❌ No numbers found. Try a different area code.")
        exit(1)
    
    print(f"Found {len(numbers)} available numbers:\n")
    for i, num in enumerate(numbers):
        location = "Unknown"
        if num.region_information:
            for r in num.region_information:
                if r.region_type == "rate_center":
                    location = r.region_name
                    break
        features = [f.name for f in num.features] if num.features else []
        print(f"  {i+1}. {num.phone_number} ({location}) - {', '.join(features)}")
    
    # Pick the first one
    chosen = numbers[0].phone_number
    print(f"\n📱 Purchasing: {chosen}")
    print("=" * 50)
    
    # Create number order
    order = client.number_orders.create(
        phone_numbers=[{"phone_number": chosen}]
    )
    
    print(f"✅ SUCCESS! Number purchased: {chosen}")
    print(f"   Order ID: {order.id}")
    print(f"   Status: {order.status}")
    print(f"\n🎉 Add this to your .env file:")
    print(f"   TELNYX_PHONE_NUMBER={chosen}")
    print(f"\n📋 Give this number to your apartment complex!")
    
except telnyx.APIError as e:
    print(f"❌ Telnyx API Error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
