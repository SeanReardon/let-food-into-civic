"""
let-food-into-civic - Automatic Call Box Unlocker

When the apartment call box rings, this service answers and plays DTMF tone "5"
repeatedly to unlock the gate for food deliveries.

Features:
- Answers calls and plays DTMF tones via TeXML
- Sends SMS notifications when gate is unlocked
"""

import logging
import os
import sys
import threading
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, Response, request, jsonify
import telnyx

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Telnyx API Key
TELNYX_API_KEY = os.getenv("LET-FOOD-INTO-CIVIC-KEY", "")

# DTMF tone configuration
UNLOCK_DIGIT = os.getenv("UNLOCK_DIGIT", "5")
TONE_DURATION_REPEATS = int(os.getenv("TONE_DURATION_REPEATS", "4"))  # ~1 second (4 x 250ms)
PAUSE_DURATION = float(os.getenv("PAUSE_DURATION", "0.2"))  # seconds
ITERATIONS = int(os.getenv("ITERATIONS", "6"))

# SMS notification configuration
# Comma-separated list of phone numbers to notify (E.164 format: +1XXXXXXXXXX)
NOTIFY_NUMBERS = [n.strip() for n in os.getenv("NOTIFY_NUMBERS", "").split(",") if n.strip()]

# Your Telnyx phone number (the one that receives calls and sends SMS)
TELNYX_PHONE_NUMBER = os.getenv("TELNYX_PHONE_NUMBER", "")

# Initialize Telnyx client
telnyx_client = telnyx.Telnyx(api_key=TELNYX_API_KEY) if TELNYX_API_KEY else None


# =============================================================================
# SMS Notification
# =============================================================================

def send_sms_notifications(caller: str, timestamp: datetime):
    """
    Send SMS notifications to configured phone numbers.
    
    Runs in a background thread to not block the webhook response.
    """
    if not NOTIFY_NUMBERS:
        logger.warning("No notification numbers configured (NOTIFY_NUMBERS is empty)")
        return
    
    if not TELNYX_PHONE_NUMBER:
        logger.warning("No Telnyx phone number configured (TELNYX_PHONE_NUMBER is empty)")
        return
    
    if not telnyx_client:
        logger.warning("Telnyx client not initialized (API key missing)")
        return
    
    time_str = timestamp.strftime("%I:%M %p")
    message = f"🍕 Gate unlocked at {time_str}! Call from: {caller}"
    
    for phone_number in NOTIFY_NUMBERS:
        try:
            logger.info(f"Sending SMS notification to {phone_number}")
            telnyx_client.messages.send(
                from_=TELNYX_PHONE_NUMBER,
                to=phone_number,
                text=message,
            )
            logger.info(f"✅ SMS sent to {phone_number}")
        except Exception as e:
            logger.error(f"❌ Failed to send SMS to {phone_number}: {e}")


def send_notifications_async(caller: str):
    """Send notifications in a background thread."""
    thread = threading.Thread(
        target=send_sms_notifications,
        args=(caller, datetime.now()),
        daemon=True
    )
    thread.start()


# =============================================================================
# TeXML Generation
# =============================================================================

def generate_unlock_texml() -> str:
    """
    Generate TeXML/TwiML response that plays DTMF tones to unlock the gate.
    
    The call box expects:
    - Tone "5" for ~1 second
    - Pause for 0.2 seconds
    - Repeat 6 times
    
    DTMF tones in TwiML/TeXML are ~250ms each, so we repeat the digit
    to achieve approximately 1 second of tone.
    """
    # Build the digit string for ~1 second of tone
    # Each digit is ~250ms, so 4 digits ≈ 1 second
    digits = UNLOCK_DIGIT * TONE_DURATION_REPEATS
    
    # Build the XML response
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<Response>']
    
    for i in range(ITERATIONS):
        # Play the DTMF tone(s)
        xml_parts.append(f'    <Play digits="{digits}"/>')
        
        # Add pause between iterations (skip pause after last iteration)
        if i < ITERATIONS - 1:
            xml_parts.append(f'    <Pause length="{PAUSE_DURATION}"/>')
    
    # Hang up after we're done
    xml_parts.append('    <Hangup/>')
    xml_parts.append('</Response>')
    
    return '\n'.join(xml_parts)


# =============================================================================
# Webhook Endpoints
# =============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for container orchestration."""
    return {
        'status': 'healthy',
        'service': 'let-food-into-civic',
        'notifications_configured': len(NOTIFY_NUMBERS) > 0,
        'telnyx_configured': bool(TELNYX_API_KEY),
    }, 200


@app.route('/webhook/voice', methods=['POST', 'GET'])
def handle_incoming_call():
    """
    Webhook endpoint for incoming voice calls.
    
    Telnyx will POST to this endpoint when a call comes in.
    We respond with TeXML instructions to play DTMF tones,
    and send SMS notifications.
    """
    # Log the incoming call
    caller = request.values.get('From', request.values.get('from', 'unknown'))
    to_number = request.values.get('To', request.values.get('to', 'unknown'))
    
    logger.info(f"📞 Incoming call from {caller} to {to_number}")
    logger.info(f"🔓 Generating unlock sequence: DTMF tone '{UNLOCK_DIGIT}' x {ITERATIONS} iterations")
    
    # Send SMS notifications asynchronously
    send_notifications_async(caller)
    
    # Generate and return the TeXML response
    texml = generate_unlock_texml()
    logger.debug(f"Response TeXML:\n{texml}")
    
    return Response(texml, mimetype='application/xml')


@app.route('/', methods=['GET'])
def index():
    """Simple landing page."""
    notify_status = f"✅ {len(NOTIFY_NUMBERS)} number(s)" if NOTIFY_NUMBERS else "❌ Not configured"
    telnyx_status = "✅ Configured" if TELNYX_API_KEY else "❌ Not configured"
    
    return f'''
    <html>
    <head>
        <title>Let Food Into Civic</title>
        <style>
            body {{
                font-family: system-ui, -apple-system, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 32px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.2);
            }}
            h1 {{ margin-top: 0; }}
            .status {{ 
                background: #f5f5f5; 
                padding: 16px; 
                border-radius: 8px;
                margin: 16px 0;
            }}
            .status p {{ margin: 8px 0; }}
            code {{
                background: #e0e0e0;
                padding: 2px 6px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🍕 Let Food Into Civic</h1>
            <p>Automatic call box unlocker for food deliveries!</p>
            <p>When the call box calls, this service answers and plays DTMF tone "{UNLOCK_DIGIT}" 
               to unlock the gate.</p>
            
            <div class="status">
                <p><strong>Service:</strong> ✅ Running</p>
                <p><strong>Telnyx API:</strong> {telnyx_status}</p>
                <p><strong>SMS Notifications:</strong> {notify_status}</p>
            </div>
            
            <p><strong>Webhook URL:</strong> <code>/webhook/voice</code></p>
        </div>
    </body>
    </html>
    '''


@app.route('/sms-consent', methods=['GET'])
def sms_consent():
    """SMS consent disclosure page for toll-free verification."""
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SMS Notification Consent - Let Food Into Civic</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f8f9fa;
                padding: 40px 20px;
            }
            .container {
                max-width: 680px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                padding: 48px;
            }
            h1 {
                font-size: 1.75rem;
                margin-bottom: 8px;
                color: #1a1a1a;
            }
            .subtitle {
                color: #666;
                margin-bottom: 32px;
                padding-bottom: 24px;
                border-bottom: 1px solid #eee;
            }
            h2 {
                font-size: 1.1rem;
                margin: 24px 0 12px 0;
                color: #1a1a1a;
            }
            p, li {
                color: #444;
                margin-bottom: 12px;
            }
            ul {
                margin-left: 24px;
                margin-bottom: 16px;
            }
            .highlight {
                background: #f0fdf4;
                border-left: 4px solid #22c55e;
                padding: 16px 20px;
                margin: 24px 0;
                border-radius: 0 8px 8px 0;
            }
            .example {
                background: #f8f9fa;
                padding: 12px 16px;
                border-radius: 8px;
                font-family: monospace;
                font-size: 0.9rem;
                margin: 12px 0;
            }
            .footer {
                margin-top: 32px;
                padding-top: 24px;
                border-top: 1px solid #eee;
                font-size: 0.85rem;
                color: #888;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 SMS Notification Consent</h1>
            <p class="subtitle">Let Food Into Civic — Delivery Gate Notifications</p>
            
            <h2>Service Description</h2>
            <p>This service provides SMS notifications to household members when the apartment 
               building gate is accessed for deliveries. When a delivery person uses the call 
               box, the system automatically unlocks the gate and sends a notification to 
               registered household members.</p>
            
            <h2>Who Receives Messages</h2>
            <p>Only household family members who have explicitly opted in receive SMS notifications. 
               This is a private, non-commercial service for personal home use.</p>
            
            <div class="highlight">
                <strong>Consent Process:</strong> Each recipient has provided explicit verbal and 
                written consent to receive delivery notifications at their registered mobile number.
            </div>
            
            <h2>Message Content</h2>
            <p>Messages are limited to delivery gate access notifications:</p>
            <div class="example">🍕 Gate unlocked at 2:30 PM! Call from: +1 (555) 123-4567</div>
            
            <h2>Message Frequency</h2>
            <ul>
                <li>Messages are sent only when the gate is accessed</li>
                <li>Typical volume: 10-30 messages per month</li>
                <li>No marketing or promotional content</li>
            </ul>
            
            <h2>Opt-Out</h2>
            <p>Recipients may opt out at any time by contacting the household administrator 
               to have their number removed from the notification list. Reply STOP to any 
               message to unsubscribe.</p>
            
            <h2>Contact</h2>
            <p>For questions about this service, contact the household administrator directly.</p>
            
            <div class="footer">
                <p>Last updated: December 2024</p>
                <p>This service is for private, personal use only.</p>
            </div>
        </div>
    </body>
    </html>
    '''


# =============================================================================
# Admin/Utility Endpoints
# =============================================================================

@app.route('/admin/test-sms', methods=['POST'])
def test_sms():
    """
    Send a test SMS to verify configuration.
    
    POST /admin/test-sms
    Body: {"to": "+1XXXXXXXXXX"} (optional, defaults to first NOTIFY_NUMBER)
    """
    if not telnyx_client:
        return jsonify({'error': 'Telnyx API key not configured'}), 500
    
    if not TELNYX_PHONE_NUMBER:
        return jsonify({'error': 'Telnyx phone number not configured'}), 500
    
    data = request.get_json() or {}
    to_number = data.get('to') or (NOTIFY_NUMBERS[0] if NOTIFY_NUMBERS else None)
    
    if not to_number:
        return jsonify({'error': 'No phone number provided and NOTIFY_NUMBERS is empty'}), 400
    
    try:
        telnyx_client.messages.send(
            from_=TELNYX_PHONE_NUMBER,
            to=to_number,
            text="🧪 Test message from let-food-into-civic! Your SMS notifications are working.",
        )
        logger.info(f"Test SMS sent to {to_number}")
        return jsonify({
            'success': True,
            'to': to_number,
        })
    except Exception as e:
        logger.error(f"Failed to send test SMS: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/call-logs', methods=['GET'])
def get_call_logs():
    """
    Query recent call logs from Telnyx.
    
    GET /admin/call-logs?limit=10
    """
    if not telnyx_client:
        return jsonify({'error': 'Telnyx API key not configured'}), 500
    
    limit = request.args.get('limit', 10, type=int)
    
    try:
        # Query call events/CDRs
        calls = telnyx_client.call_events.list(page_size=limit)
        
        call_list = []
        for call in calls.data:
            call_list.append({
                'id': getattr(call, 'id', 'N/A'),
                'from': getattr(call, 'from_', getattr(call, 'caller_id_number', 'N/A')),
                'to': getattr(call, 'to', getattr(call, 'destination_number', 'N/A')),
                'type': getattr(call, 'event_type', 'N/A'),
                'occurred_at': str(getattr(call, 'occurred_at', 'N/A')),
            })
        
        return jsonify({'calls': call_list, 'count': len(call_list)})
    except Exception as e:
        logger.error(f"Failed to fetch call logs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/buy-number', methods=['POST'])
def buy_number():
    """
    Search for available phone numbers.
    
    POST /admin/buy-number
    Body: {
        "area_code": "415",      # Optional: area code to search
        "country": "US"          # Optional: country code (default: US)
    }
    """
    if not telnyx_client:
        return jsonify({'error': 'Telnyx API key not configured'}), 500
    
    data = request.get_json() or {}
    area_code = data.get('area_code', '214')
    country = data.get('country', 'US')
    
    try:
        # Search for available numbers
        response = telnyx_client.available_phone_numbers.list(
            filter={
                'country_code': country,
                'national_destination_code': area_code,
                'limit': 5,
            }
        )
        
        if not response.data:
            return jsonify({'error': 'No numbers found matching criteria'}), 404
        
        # Return available numbers for selection
        numbers = []
        for n in response.data:
            location = "Unknown"
            if n.region_information:
                for r in n.region_information:
                    if r.region_type == "rate_center":
                        location = r.region_name
                        break
            numbers.append({
                'phone_number': n.phone_number,
                'location': location,
                'monthly_cost': n.cost_information.monthly_cost if n.cost_information else 'N/A',
            })
        
        return jsonify({
            'available_numbers': numbers,
            'message': 'Use POST /admin/buy-number/confirm with {"phone_number": "..."} to purchase',
        })
    except Exception as e:
        logger.error(f"Failed to search numbers: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/buy-number/confirm', methods=['POST'])
def confirm_buy_number():
    """
    Confirm purchase of a specific phone number.
    
    POST /admin/buy-number/confirm
    Body: {"phone_number": "+14155551234"}
    """
    if not telnyx_client:
        return jsonify({'error': 'Telnyx API key not configured'}), 500
    
    data = request.get_json() or {}
    phone_number = data.get('phone_number')
    
    if not phone_number:
        return jsonify({'error': 'phone_number is required'}), 400
    
    try:
        # Order the phone number
        order = telnyx_client.number_orders.create(
            phone_numbers=[{'phone_number': phone_number}]
        )
        
        logger.info(f"📱 Purchased phone number: {phone_number}")
        
        return jsonify({
            'success': True,
            'phone_number': phone_number,
            'message': 'Number purchased! Remember to set up messaging profile for SMS.',
        })
    except Exception as e:
        logger.error(f"Failed to purchase number: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for the service."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info("🍕 let-food-into-civic starting up...")
    logger.info(f"Configuration:")
    logger.info(f"  - Unlock digit: {UNLOCK_DIGIT}")
    logger.info(f"  - Tone repeats: {TONE_DURATION_REPEATS} (~{TONE_DURATION_REPEATS * 0.25}s)")
    logger.info(f"  - Pause duration: {PAUSE_DURATION}s")
    logger.info(f"  - Iterations: {ITERATIONS}")
    logger.info(f"  - Telnyx API: {'✅ Configured' if TELNYX_API_KEY else '❌ Not configured'}")
    logger.info(f"  - Telnyx number: {TELNYX_PHONE_NUMBER or 'Not configured'}")
    logger.info(f"  - Notify numbers: {NOTIFY_NUMBERS or 'None configured'}")
    logger.info(f"  - Listening on: {host}:{port}")
    
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
