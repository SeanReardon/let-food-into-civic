#!/bin/bash
# Check status of all Telnyx verifications/campaigns
cd /home/seanr/dev/let-food-into-civic

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║     🔍 Telnyx Status Check                ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# Check toll-free verification
./check_1888_status.sh

echo ""

# Check 10DLC campaign
./check_10dlc_status.sh

echo ""
echo "─────────────────────────────────────────"
echo "  Run './check_status.sh' again to refresh"
echo ""
