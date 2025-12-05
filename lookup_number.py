#!/usr/bin/env python3
"""
Look up information about a phone number using Telnyx Number Lookup API.

Usage:
    ./lookup_number.py +12145551234
    ./lookup_number.py 2145551234
"""

import os
import sys
import re
from dotenv import load_dotenv
import telnyx

load_dotenv()

api_key = os.getenv("TELNYX_LET_FOOD_INTO_CIVIC_KEY")
if not api_key:
    print("❌ TELNYX_LET_FOOD_INTO_CIVIC_KEY not set in .env")
    sys.exit(1)

client = telnyx.Telnyx(api_key=api_key)


def normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format (+1XXXXXXXXXX)."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        digits = '1' + digits
    if len(digits) == 11 and digits.startswith('1'):
        return '+' + digits
    return '+' + digits


def lookup_number(phone: str):
    """Look up a phone number and display results."""
    normalized = normalize_phone(phone)
    
    print(f"\n🔍 Looking up: {normalized}")
    print("=" * 50)
    
    try:
        # Use httpx directly since the SDK might not have number_lookup
        import httpx
        
        response = httpx.get(
            f"https://api.telnyx.com/v2/number_lookup/{normalized}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            print(response.text)
            return
        
        data = response.json().get('data', {})
        
        # Basic info
        print(f"\n📱 Number: {data.get('phone_number', 'N/A')}")
        print(f"   Format: {data.get('national_format', 'N/A')}")
        print(f"   Country: {data.get('country_code', 'N/A')}")
        print(f"   Valid: {'✅ Yes' if data.get('valid_number') else '❌ No'}")
        
        # Caller Name (CNAM) - if available
        caller_name = data.get('caller_name')
        if caller_name:
            print(f"\n👤 Caller Name (CNAM):")
            print(f"   Name: {caller_name.get('caller_name', 'N/A')}")
            print(f"   Error: {caller_name.get('error_code', 'None')}")
        
        # Carrier info
        carrier = data.get('carrier')
        if carrier:
            print(f"\n📡 Carrier:")
            print(f"   Name: {carrier.get('name', 'N/A')}")
            print(f"   Type: {carrier.get('type', 'N/A')}")
        
        # Portability info (usually populated)
        portability = data.get('portability', {})
        if portability:
            print(f"\n🔀 Portability/Network Info:")
            print(f"   Carrier: {portability.get('spid_carrier_name', 'N/A')}")
            print(f"   Line Type: {portability.get('line_type', 'N/A')}")
            print(f"   City: {portability.get('city', 'N/A')}")
            print(f"   State: {portability.get('state', 'N/A')}")
            print(f"   OCN: {portability.get('ocn', 'N/A')}")
            if portability.get('ported_status'):
                print(f"   Ported: {portability.get('ported_status')}")
                if portability.get('ported_date'):
                    print(f"   Ported Date: {portability.get('ported_date')}")
        
        # Fraud score - if available
        fraud = data.get('fraud')
        if fraud:
            print(f"\n⚠️  Fraud Score:")
            print(f"   Score: {fraud.get('score', 'N/A')}")
        
        print("\n" + "=" * 50)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ./lookup_number.py <phone_number>")
        print("Example: ./lookup_number.py +12145551234")
        print("         ./lookup_number.py 2145551234")
        sys.exit(1)
    
    lookup_number(sys.argv[1])

