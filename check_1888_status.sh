#!/bin/bash
# Check toll-free verification status for +18889090319
cd /home/seanr/dev/let-food-into-civic
export $(cat .env | grep -v '^#' | xargs)

echo "📞 Toll-Free Verification"
echo "─────────────────────────────────────────"

python3 -c "
import os
from dotenv import load_dotenv
import telnyx

load_dotenv()
client = telnyx.Telnyx(api_key=os.getenv('TELNYX_LET_FOOD_INTO_CIVIC_KEY'))

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
"
