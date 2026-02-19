#!/usr/bin/env python3
"""
Check Telnyx call logs for calls around 2 AM on 2025-12-22
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
from datetime import datetime

load_dotenv()

api_key = os.getenv("TELNYX_LET_FOOD_INTO_CIVIC_KEY")
if not api_key:
    print("❌ TELNYX_LET_FOOD_INTO_CIVIC_KEY not set")
    exit(1)

client = telnyx.Telnyx(api_key=api_key)

print("📞 Checking Telnyx Call Logs")
print("=" * 60)
print("Looking for calls on 2025-12-22 around 2 AM CST (08:00 UTC)")
print("=" * 60)

try:
    import httpx
    
    # Check CDRs (Call Detail Records) which are more complete
    print("\nChecking CDRs (Call Detail Records)...")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Get CDRs for 2025-12-22
    response = httpx.get(
        "https://api.telnyx.com/v2/call_control_applications",
        headers=headers,
        params={
            "filter[started_at][gte]": "2025-12-22T00:00:00Z",
            "filter[started_at][lte]": "2025-12-22T23:59:59Z",
        }
    )
    
    # Try CDRs endpoint directly
    cdr_response = httpx.get(
        "https://api.telnyx.com/v2/cdr",
        headers=headers,
        params={
            "filter[started_at][gte]": "2025-12-22T00:00:00Z",
            "filter[started_at][lte]": "2025-12-22T23:59:59Z",
            "page[size]": 50
        }
    )
    
    if cdr_response.status_code == 200:
        data = cdr_response.json()
        cdrs = data.get('data', [])
        print(f"\nFound {len(cdrs)} CDR records for 2025-12-22:\n")
        
        for cdr in cdrs:
            started_at = cdr.get('started_at', 'N/A')
            from_num = cdr.get('from', cdr.get('call_leg_id', 'N/A'))
            to_num = cdr.get('to', cdr.get('destination_number', 'N/A'))
            direction = cdr.get('direction', 'N/A')
            status = cdr.get('status', 'N/A')
            duration = cdr.get('duration_seconds', 'N/A')
            
            print(f"📞 CDR:")
            print(f"   Time: {started_at}")
            print(f"   From: {from_num}")
            print(f"   To: {to_num}")
            print(f"   Direction: {direction}")
            print(f"   Status: {status}")
            print(f"   Duration: {duration}s")
            print()
    else:
        print(f"⚠️  CDR API returned: {cdr_response.status_code}")
        print(f"   Response: {cdr_response.text[:200]}")
        
        # Fallback to call events
        print("\nFalling back to call events...")
        calls = client.call_events.list()
        
        print(f"\nFound {len(calls.data)} recent call events:\n")
        
        calls_found = False
        for call in calls.data:
            occurred_at = getattr(call, 'occurred_at', None)
            if occurred_at and '2025-12-22' in str(occurred_at):
                calls_found = True
                from_num = getattr(call, 'from_', getattr(call, 'caller_id_number', 'N/A'))
                to_num = getattr(call, 'to', getattr(call, 'destination_number', 'N/A'))
                event_type = getattr(call, 'event_type', 'N/A')
                call_id = getattr(call, 'id', 'N/A')
                
                print(f"📞 Call Event:")
                print(f"   Time: {occurred_at}")
                print(f"   From: {from_num}")
                print(f"   To: {to_num}")
                print(f"   Type: {event_type}")
                print(f"   ID: {call_id}")
                print()
        
        if not calls_found:
            print("⚠️  No calls found for 2025-12-22 in call events")
            print("\nMost recent call events:")
            for call in calls.data[:5]:
                occurred_at = getattr(call, 'occurred_at', 'N/A')
                from_num = getattr(call, 'from_', getattr(call, 'caller_id_number', 'N/A'))
                to_num = getattr(call, 'to', getattr(call, 'destination_number', 'N/A'))
                print(f"   {occurred_at} - From: {from_num} To: {to_num}")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

