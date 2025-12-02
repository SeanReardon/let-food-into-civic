#!/bin/bash
cd /home/seanr/dev/let-food-into-civic
export $(cat .env | grep -v '^#' | xargs)

echo "📊 10DLC Campaign Status"
echo "========================"

# Check campaign status
STATUS=$(curl -s -X GET "https://api.telnyx.com/10dlc/campaign/4b30019a-e14d-522f-fc8e-8a26e86a7e54" \
  -H "Authorization: Bearer $TELNYX_LET_FOOD_INTO_CIVIC_KEY" \
  -H "Content-Type: application/json")

echo "$STATUS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Campaign: {d.get('status', 'unknown')}\")
print(f\"TCR Status: {d.get('campaignStatus', 'unknown')}\")
print(f\"T-Mobile Registered: {d.get('isTMobileRegistered', False)}\")
"

# Try to assign number if T-Mobile is registered
TMOBILE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('isTMobileRegistered', False))")

if [ "$TMOBILE" = "True" ]; then
    echo ""
    echo "✅ T-Mobile registered! Assigning phone number..."
    curl -s -X POST "https://api.telnyx.com/10dlc/phoneNumberCampaign" \
      -H "Authorization: Bearer $TELNYX_LET_FOOD_INTO_CIVIC_KEY" \
      -H "Content-Type: application/json" \
      -d '{"phoneNumber": "+12148170664", "campaignId": "4b30019a-e14d-522f-fc8e-8a26e86a7e54"}' | python3 -m json.tool
else
    echo ""
    echo "⏳ T-Mobile not registered yet. Check back later."
fi
