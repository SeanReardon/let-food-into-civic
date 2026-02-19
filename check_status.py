#!/usr/bin/env python3
"""
Check status of all Telnyx verifications/campaigns
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
if not api_key:
    print("❌ TELNYX_LET_FOOD_INTO_CIVIC_KEY not set in .env")
    sys.exit(1)

client = telnyx.Telnyx(api_key=api_key)

print("")
print("╔═══════════════════════════════════════════╗")
print("║     🔍 Telnyx Status Check                ║")
print("╚═══════════════════════════════════════════╝")
print("")

# Check toll-free verification
print("📞 Toll-Free Verification")
print("─────────────────────────────────────────")

request_id = 'a4e3760b-a5e3-5365-b33b-c161e2d61d2b'
try:
    r = client.messaging_tollfree.verification.requests.retrieve(request_id)
    
    status = r.verification_status
    if status == 'Approved':
        emoji = '✅'
    elif 'Waiting' in status or 'Pending' in status:
        emoji = '🟡'
    elif 'Rejected' in status or 'Failed' in status:
        emoji = '❌'
    else:
        emoji = '⚪'
    
    print(f'  Phone:      {r.phone_numbers[0].phone_number}')
    print(f'  Status:     {emoji} {status}')
    print(f'  Business:   {r.business_name}')
    print(f'  Use Case:   {r.use_case}')
    print(f'  Created:    {str(r.created_at)[:10]}')
    print(f'  Updated:    {str(r.updated_at)[:10]}')
    
    if r.reason:
        print(f'  Reason:     {r.reason}')
        
except Exception as e:
    print(f'  Error: {e}')

print("")

# Check 10DLC campaign
print("📱 10DLC Campaign")
print("─────────────────────────────────────────")

campaign_id = '4b30019a-e14d-522f-fc8e-8a26e86a7e54'
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

try:
    response = httpx.get(
        f"https://api.telnyx.com/10dlc/campaign/{campaign_id}",
        headers=headers
    )
    response.raise_for_status()
    d = response.json()
    
    campaign_status = d.get('campaignStatus', 'unknown')
    tmobile = d.get('isTMobileRegistered', False)
    phone_numbers = d.get('phoneNumbers', [])
    tcr_id = d.get('tcrCampaignId', 'N/A')
    failures = d.get('failureReasons', [])
    
    # Determine emoji based on status
    if campaign_status in ['ACTIVE', 'TCR_ACCEPTED']:
        if tmobile:
            emoji = '✅'
        else:
            emoji = '🟡'
    elif 'FAILED' in campaign_status or 'REJECTED' in campaign_status:
        emoji = '❌'
    else:
        emoji = '⚪'
    
    print(f'  Phone:      +12148170664')
    print(f'  Status:     {emoji} {campaign_status}')
    print(f'  TCR ID:     {tcr_id}')
    print(f'  T-Mobile:   {"✅ Registered" if tmobile else "⏳ Pending"}')
    print(f'  Numbers:    {len(phone_numbers)} assigned')
    
    # Show failure reasons if any
    if failures and 'FAILED' in campaign_status:
        reason = failures[0].get('description', 'Unknown')[:80]
        print(f'  Reason:     {reason}...')
    
    # Summary
    print()
    if tmobile:
        if len(phone_numbers) > 0:
            print('  🎉 Ready to send SMS!')
        else:
            print('  ✅ T-Mobile registered! Assigning number...')
    elif 'FAILED' in campaign_status:
        print('  ❌ Campaign failed review.')
    else:
        print('  ⏳ Waiting for T-Mobile registration...')
    
    # If T-Mobile is registered, try to assign the phone number
    if tmobile and len(phone_numbers) == 0:
        print("")
        print("  🔧 Assigning phone number to campaign...")
        assign_response = httpx.post(
            "https://api.telnyx.com/10dlc/phoneNumberCampaign",
            headers=headers,
            json={
                "phoneNumber": "+12148170664",
                "campaignId": campaign_id
            }
        )
        
        if assign_response.status_code == 200:
            print("  ✅ Phone number assigned successfully!")
        else:
            try:
                error_data = assign_response.json()
                error_detail = error_data.get("errors", [{}])[0].get("detail", str(error_data))[:60]
                print(f"  ⚠️  {error_detail}")
            except:
                print(f"  ⚠️  {assign_response.text[:60]}")
                
except Exception as e:
    print(f'  Error: {e}')

print("")
print("─────────────────────────────────────────")
print("  Run 'python check_status.py' again to refresh")
print("")

