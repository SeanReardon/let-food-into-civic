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
TELNYX_API_KEY = os.getenv("TELNYX_LET_FOOD_INTO_CIVIC_KEY", "")

# DTMF tone configuration
UNLOCK_DIGIT = os.getenv("UNLOCK_DIGIT", "5")
TONE_DURATION_REPEATS = int(os.getenv("TONE_DURATION_REPEATS", "8"))  # ~2 seconds (8 x 250ms)
PAUSE_DURATION = float(os.getenv("PAUSE_DURATION", "0.5"))  # seconds
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
    logger.info(f"📱 SMS notification function called for caller: {caller} at {timestamp}")
    
    if not NOTIFY_NUMBERS:
        logger.warning("⚠️  No notification numbers configured (NOTIFY_NUMBERS is empty)")
        return
    
    if not TELNYX_PHONE_NUMBER:
        logger.warning("⚠️  No Telnyx phone number configured (TELNYX_PHONE_NUMBER is empty)")
        return
    
    if not telnyx_client:
        logger.warning("⚠️  Telnyx client not initialized (API key missing)")
        return
    
    message = "the civic callbox was answered and I did 5s, <3 lfic."
    logger.info(f"📝 SMS message: {message}")
    logger.info(f"📋 Sending to {len(NOTIFY_NUMBERS)} recipient(s): {NOTIFY_NUMBERS}")
    
    success_count = 0
    failure_count = 0
    
    for phone_number in NOTIFY_NUMBERS:
        try:
            logger.info(f"📤 Attempting to send SMS to {phone_number}...")
            telnyx_client.messages.send(
                from_=TELNYX_PHONE_NUMBER,
                to=phone_number,
                text=message,
            )
            logger.info(f"✅ SMS successfully sent to {phone_number}")
            success_count += 1
        except Exception as e:
            logger.error(f"❌ Failed to send SMS to {phone_number}: {e}", exc_info=True)
            failure_count += 1
    
    logger.info(f"📊 SMS notification summary: {success_count} succeeded, {failure_count} failed out of {len(NOTIFY_NUMBERS)} total")


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

# URL to the 2-second DTMF tone audio file
DTMF_AUDIO_URL = os.getenv(
    "DTMF_AUDIO_URL",
    "https://let-food-into-civic.contrived.com/static/dtmf5-2sec.wav"
)

def generate_unlock_texml() -> str:
    """
    Generate TeXML/TwiML response that plays DTMF tones to unlock the gate.
    
    The call box expects:
    - Tone "5" held for ~2 seconds
    - Pause for 0.5 seconds
    - Repeat 6 times
    
    We use a pre-recorded DTMF audio file because TwiML's <Play digits>
    only supports short (~100ms) tones. The audio file contains a 2-second
    DTMF "5" tone (770 Hz + 1336 Hz).
    """
    # Build the XML response using audio file for proper duration
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<Response>']
    
    for i in range(ITERATIONS):
        # Play the DTMF tone audio file
        xml_parts.append(f'    <Play>{DTMF_AUDIO_URL}</Play>')
        
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
    # Log the incoming call with full details
    caller = request.values.get('From', request.values.get('from', 'unknown'))
    to_number = request.values.get('To', request.values.get('to', 'unknown'))
    call_id = request.values.get('CallSid', request.values.get('call_sid', 'unknown'))
    
    logger.info("=" * 60)
    logger.info(f"📞 INCOMING CALL RECEIVED")
    logger.info(f"   Call ID: {call_id}")
    logger.info(f"   From: {caller}")
    logger.info(f"   To: {to_number}")
    logger.info(f"   Timestamp: {datetime.now().isoformat()}")
    logger.info(f"🔓 Generating unlock sequence: DTMF tone '{UNLOCK_DIGIT}' x {ITERATIONS} iterations")
    
    # Send SMS notifications asynchronously
    logger.info(f"📱 Initiating SMS notification to {len(NOTIFY_NUMBERS)} recipient(s)")
    send_notifications_async(caller)
    
    # Generate and return the TeXML response
    texml = generate_unlock_texml()
    logger.debug(f"Response TeXML:\n{texml}")
    logger.info(f"✅ TeXML response generated and sent")
    logger.info("=" * 60)
    
    return Response(texml, mimetype='application/xml')


@app.route('/', methods=['GET'])
def index():
    """Public landing page for Telnyx verification."""
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Let Food Into Civic — Home Delivery Notifications by Contrived LLC</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            
            :root {
                --bg: #fafaf9;
                --bg-alt: #ffffff;
                --text: #1c1917;
                --text-secondary: #57534e;
                --text-muted: #a8a29e;
                --accent: #b45309;
                --accent-light: #fef3c7;
                --border: #e7e5e4;
                --link: #0369a1;
            }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: var(--bg);
                color: var(--text);
                min-height: 100vh;
                line-height: 1.7;
                font-size: 16px;
            }
            
            .container {
                max-width: 680px;
                margin: 0 auto;
                padding: 80px 24px;
            }
            
            header {
                text-align: center;
                margin-bottom: 64px;
                padding-bottom: 48px;
                border-bottom: 1px solid var(--border);
            }
            
            .logo {
                font-size: 2.5rem;
                margin-bottom: 20px;
                display: inline-block;
            }
            
            h1 {
                font-family: 'Source Serif 4', Georgia, serif;
                font-size: 2.25rem;
                font-weight: 600;
                margin-bottom: 12px;
                letter-spacing: -0.02em;
                color: var(--text);
            }
            
            .tagline {
                color: var(--text-secondary);
                font-size: 1.1rem;
            }
            
            .content {
                margin-bottom: 48px;
            }
            
            .content h2 {
                font-family: 'Source Serif 4', Georgia, serif;
                font-size: 1.5rem;
                font-weight: 600;
                margin-bottom: 20px;
                margin-top: 48px;
                color: var(--text);
            }
            
            .content h2:first-child {
                margin-top: 0;
            }
            
            .content p {
                color: var(--text-secondary);
                margin-bottom: 20px;
            }
            
            .content ul {
                color: var(--text-secondary);
                margin-bottom: 20px;
                margin-left: 24px;
            }
            
            .content li {
                margin-bottom: 8px;
            }
            
            .highlight-box {
                background: var(--accent-light);
                border-left: 4px solid var(--accent);
                padding: 20px 24px;
                margin: 32px 0;
                border-radius: 0 8px 8px 0;
            }
            
            .highlight-box p {
                color: var(--text);
                margin-bottom: 0;
            }
            
            .links-section {
                background: var(--bg-alt);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 32px;
                margin: 48px 0;
            }
            
            .links-section h3 {
                font-family: 'Source Serif 4', Georgia, serif;
                font-size: 1.1rem;
                font-weight: 600;
                margin-bottom: 20px;
                color: var(--text);
            }
            
            .links-grid {
                display: grid;
                gap: 16px;
            }
            
            .links-grid a {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 16px 20px;
                background: var(--bg);
                border: 1px solid var(--border);
                border-radius: 8px;
                color: var(--text);
                text-decoration: none;
                transition: all 0.2s;
            }
            
            .links-grid a:hover {
                border-color: var(--accent);
                background: var(--accent-light);
            }
            
            .links-grid a svg {
                width: 24px;
                height: 24px;
                color: var(--accent);
                flex-shrink: 0;
            }
            
            .links-grid .link-content {
                flex: 1;
            }
            
            .links-grid .link-title {
                font-weight: 600;
                margin-bottom: 2px;
            }
            
            .links-grid .link-desc {
                font-size: 0.875rem;
                color: var(--text-muted);
            }
            
            footer {
                text-align: center;
                margin-top: 64px;
                padding-top: 32px;
                border-top: 1px solid var(--border);
                color: var(--text-muted);
                font-size: 0.875rem;
            }
            
            footer a {
                color: var(--text-secondary);
                text-decoration: none;
            }
            
            footer a:hover {
                color: var(--accent);
            }
            
            footer p {
                margin-bottom: 8px;
            }
            
            @media (max-width: 600px) {
                .container {
                    padding: 48px 20px;
                }
                h1 {
                    font-size: 1.75rem;
                }
                .content h2 {
                    font-size: 1.25rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="logo">🏠</div>
                <h1>Let Food Into Civic</h1>
                <p class="tagline">Home Delivery Notification Service</p>
            </header>
            
            <div class="content">
                <h2>About This Service</h2>
                <p>
                    Welcome to <strong>Let Food Into Civic</strong>, a home notification service 
                    designed and operated by Contrived LLC. This service provides real-time SMS 
                    notifications to household members when deliveries arrive at their residence.
                </p>
                <p>
                    In today's busy world, keeping track of package and food deliveries can be 
                    challenging. Whether you're working from home, managing a household, or simply 
                    want to know when your order has arrived, timely notifications help ensure you 
                    never miss an important delivery.
                </p>
                
                <h2>Who We Serve</h2>
                <p>
                    This is a <strong>private, non-commercial service</strong> created specifically 
                    for personal household use. We provide delivery notifications exclusively to 
                    household members who have explicitly opted in to receive text message alerts. 
                    Our service is not available to the general public and operates solely for 
                    the benefit of registered family members at a single residential address.
                </p>
                
                <div class="highlight-box">
                    <p>
                        <strong>Privacy First:</strong> We take your privacy seriously. Only household 
                        members who have provided explicit consent receive notifications. Your phone 
                        number and personal information are never shared with third parties or used 
                        for marketing purposes.
                    </p>
                </div>
                
                <h2>How Notifications Work</h2>
                <p>
                    When a delivery arrives at the registered address, our system automatically 
                    sends an SMS notification to all opted-in household members. These notifications 
                    include the time of the delivery event so you always know exactly when something 
                    has arrived.
                </p>
                <p>
                    Message frequency varies based on delivery activity at your residence. Most 
                    households can expect to receive between 10-30 messages per month, though this 
                    depends entirely on how many deliveries you receive. Standard message and data 
                    rates from your mobile carrier may apply.
                </p>
                
                <h2>Your Rights &amp; Choices</h2>
                <p>
                    We believe in giving you complete control over your notification preferences. 
                    As a registered user of this service, you have several important rights:
                </p>
                <ul>
                    <li><strong>Opt-Out Anytime:</strong> Simply reply STOP to any message to immediately unsubscribe from all future notifications.</li>
                    <li><strong>Get Help:</strong> Reply HELP to any message for assistance or contact information.</li>
                    <li><strong>Transparency:</strong> We clearly disclose how your information is used in our privacy policy.</li>
                    <li><strong>No Obligations:</strong> Your consent to receive messages is not a condition of any purchase or service.</li>
                </ul>
                
                <h2>About Contrived LLC</h2>
                <p>
                    This service is owned and operated by <strong>Contrived LLC</strong>, a Texas-based 
                    company focused on building practical technology solutions for everyday life. We 
                    created Let Food Into Civic to solve a simple problem: making sure busy families 
                    never miss an important delivery.
                </p>
                <p>
                    For any questions about this service, our company, or how we handle your information, 
                    please don't hesitate to reach out to us at sean.reardon@contrived.com.
                </p>
            </div>
            
            <div class="links-section">
                <h3>Important Information</h3>
                <div class="links-grid">
                    <a href="https://let-food-into-civic.contrived.com/sms-consent">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                        </svg>
                        <div class="link-content">
                            <div class="link-title">SMS Consent &amp; Disclosures</div>
                            <div class="link-desc">View our complete SMS messaging terms, CTIA disclosures, and opt-in information</div>
                        </div>
                    </a>
                    <a href="https://contrived.com/privacy">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                        <div class="link-content">
                            <div class="link-title">Privacy Policy</div>
                            <div class="link-desc">Learn how we collect, use, and protect your personal information</div>
                        </div>
                    </a>
                </div>
            </div>
            
            <footer>
                <p>&copy; 2024 <a href="https://contrived.com">Contrived LLC</a>. All rights reserved.</p>
                <p>A home automation service for private, residential use.</p>
                <p style="margin-top: 16px;">
                    <a href="https://contrived.com/privacy">Privacy Policy</a> · 
                    <a href="https://let-food-into-civic.contrived.com/sms-consent">SMS Terms</a> · 
                    <a href="mailto:sean.reardon@contrived.com">Contact Us</a>
                </p>
            </footer>
        </div>
    </body>
    </html>
    '''


@app.route('/status', methods=['GET'])
def status():
    """Internal status page showing configuration."""
    notify_status = f"✅ {len(NOTIFY_NUMBERS)} number(s)" if NOTIFY_NUMBERS else "❌ Not configured"
    telnyx_status = "✅ Configured" if TELNYX_API_KEY else "❌ Not configured"
    
    return f'''
    <html>
    <head>
        <title>Let Food Into Civic - Status</title>
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
    """SMS consent disclosure page for toll-free verification with CTIA-required disclosures."""
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
            .ctia-disclosure {
                background: #fef3c7;
                border: 1px solid #f59e0b;
                padding: 20px;
                margin: 24px 0;
                border-radius: 8px;
            }
            .ctia-disclosure h3 {
                color: #92400e;
                margin-bottom: 12px;
                font-size: 1rem;
            }
            .ctia-disclosure ul {
                margin-bottom: 0;
            }
            .ctia-disclosure li {
                margin-bottom: 8px;
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
                <strong>Consent Process:</strong> By providing your mobile phone number and agreeing 
                to receive notifications, you consent to receive automated SMS messages about 
                delivery gate access at the registered address. Consent is not a condition of 
                any purchase.
            </div>
            
            <div class="ctia-disclosure">
                <h3>📋 Important Disclosures (CTIA Compliance)</h3>
                <ul>
                    <li><strong>Message Frequency:</strong> Message frequency varies based on delivery activity. Expect approximately 10-30 messages per month.</li>
                    <li><strong>Message and Data Rates:</strong> Message and data rates may apply. Check with your mobile carrier for details.</li>
                    <li><strong>Opt-Out:</strong> Reply <strong>STOP</strong> to any message to unsubscribe and stop receiving notifications.</li>
                    <li><strong>Help:</strong> Reply <strong>HELP</strong> for assistance or contact the household administrator.</li>
                    <li><strong>Privacy:</strong> Your phone number will not be shared with third parties. See our <a href="https://contrived.com/privacy">Privacy Policy</a> for details.</li>
                </ul>
            </div>
            
            <h2>Message Content</h2>
            <p>Messages are limited to delivery gate access notifications:</p>
            <div class="example">🍕 Gate unlocked at 2:30 PM! Call from: +1 (555) 123-4567</div>
            
            <h2>Opt-Out Instructions</h2>
            <p>You may opt out at any time by:</p>
            <ul>
                <li>Replying <strong>STOP</strong> to any message</li>
                <li>Contacting the household administrator to have your number removed</li>
            </ul>
            <p>After opting out, you will receive a confirmation message and no further notifications.</p>
            
            <h2>Contact &amp; Support</h2>
            <p>For questions about this service:</p>
            <ul>
                <li>Reply <strong>HELP</strong> to any message</li>
                <li>Email: sean.reardon@contrived.com</li>
            </ul>
            
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
