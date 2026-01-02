#!/bin/bash
# Check 10DLC campaign status for +12148170664
cd /home/seanr/dev/let-food-into-civic
export $(cat .env | grep -v '^#' | xargs)

echo "📱 10DLC Campaign"
echo "─────────────────────────────────────────"

# Check campaign status using curl + python for parsing
STATUS=$(curl -s -X GET "https://api.telnyx.com/10dlc/campaign/4b30019a-e14d-522f-fc8e-8a26e86a7e54" \
  -H "Authorization: Bearer $TELNYX_LET_FOOD_INTO_CIVIC_KEY" \
  -H "Content-Type: application/json")

echo "$STATUS" | python3 -c "
import sys, json

d = json.load(sys.stdin)

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
print(f'  T-Mobile:   {\"✅ Registered\" if tmobile else \"⏳ Pending\"}')
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
"

# If T-Mobile is registered, try to assign the phone number
TMOBILE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('isTMobileRegistered', False))")

if [ "$TMOBILE" = "True" ]; then
    echo ""
    echo "  🔧 Assigning phone number to campaign..."
    RESULT=$(curl -s -X POST "https://api.telnyx.com/10dlc/phoneNumberCampaign" \
      -H "Authorization: Bearer $TELNYX_LET_FOOD_INTO_CIVIC_KEY" \
      -H "Content-Type: application/json" \
      -d '{"phoneNumber": "+12148170664", "campaignId": "4b30019a-e14d-522f-fc8e-8a26e86a7e54"}')
    
    if echo "$RESULT" | grep -q "error"; then
        echo "  ⚠️  $(echo $RESULT | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("errors", [{}])[0].get("detail", str(d))[:60])')"
    else
        echo "  ✅ Phone number assigned successfully!"
    fi
fi
