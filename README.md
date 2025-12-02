# 🍕 Let Food Into Civic

Automatic call box unlocker for food deliveries! When your apartment call box rings, this service answers and plays DTMF tone "5" to unlock the gate, then sends you an SMS notification.

## How It Works

```
[Delivery Person at Gate]
        ↓
[Call Box Dials Your Telnyx Number]
        ↓
[Telnyx Receives Call → Sends Webhook to Your Server]
        ↓
[Server Returns TeXML: "Play DTMF 5, pause, repeat 6x"]
        ↓
[Gate Unlocks! 🎉]
        ↓
[SMS sent to you & your wife: "🍕 Gate unlocked!"]
        ↓
[Food Arrives 🍕]
```

## Features

- 📞 **Auto-answer calls** and play DTMF tones to unlock gate
- 📱 **SMS notifications** to multiple phone numbers when gate unlocks
- 📊 **Call logs** - query recent calls via API
- 🛒 **Buy numbers** - search and purchase phone numbers programmatically
- 🔒 **Secure** - webhook signature validation

## Setup Guide

### 1. Create a Telnyx Account

1. Go to [telnyx.com](https://telnyx.com) and sign up
2. You'll get **$10 free credit** which is plenty for testing
3. Verify your account (may require ID verification)

### 2. Get Your API Key

1. In the Telnyx portal, go to **API Keys** (under account settings)
2. Create a new API key
3. Copy it - you'll need it for the `.env` file

### 3. Buy a Phone Number

1. Go to **Numbers → Search & Buy**
2. Search for a local number in your area code
3. Buy the number (~$1/month)
4. Note the phone number - you'll need it for the `.env` file

### 4. Create a TeXML Application

1. Go to **Voice → TeXML Applications** in the Telnyx portal
2. Click **Create TeXML Application**
3. Name it something like "Call Box Unlocker"
4. Set the **Voice URL** to: `https://callbox.contrived.com/webhook/voice`
   - Replace `callbox.contrived.com` with your actual domain
5. Set the **Voice Method** to `POST`
6. Save the application

### 5. Assign the Phone Number to the Application

1. Go to **Numbers → My Numbers**
2. Click on your phone number
3. Under **Voice Settings**, select your TeXML Application
4. Save changes

### 6. Enable Messaging on Your Number

1. Go to **Numbers → My Numbers**
2. Click on your phone number
3. Under **Messaging Settings**, enable messaging
4. This allows the number to send SMS notifications

### 7. Configure Your Environment

Create a `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Your Telnyx API key
LET-FOOD-INTO-CIVIC-KEY=KEY017xxxxxxxxxxxxxxxxxxxxx

# Your Telnyx phone number (E.164 format)
TELNYX_PHONE_NUMBER=+14155551234

# Phone numbers to notify (you and your wife)
NOTIFY_NUMBERS=+14155551111,+14155552222
```

### 8. Deploy the Service

On your homelab server:

```bash
# Create the webroot for certbot
sudo mkdir -p /var/www/callbox.contrived.com/html

# Get SSL certificate
sudo certbot certonly --webroot -w /var/www/callbox.contrived.com/html -d callbox.contrived.com

# Enable the nginx site
sudo ln -s /etc/nginx/sites-available/callbox.contrived.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Start the service
cd /path/to/let-food-into-civic
docker compose up -d
```

### 9. Update Your Apartment

Give your apartment management the new Telnyx phone number!

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LET-FOOD-INTO-CIVIC-KEY` | Yes | Your Telnyx API key |
| `TELNYX_PHONE_NUMBER` | Yes | Your Telnyx phone number (E.164 format) |
| `NOTIFY_NUMBERS` | No | Comma-separated phone numbers for SMS notifications |
| `UNLOCK_DIGIT` | No | DTMF digit to play (default: `5`) |
| `TONE_DURATION_REPEATS` | No | How many times to repeat digit (default: `4`) |
| `PAUSE_DURATION` | No | Seconds to pause between tone bursts (default: `0.2`) |
| `ITERATIONS` | No | How many times to repeat the full sequence (default: `6`) |
| `LOG_LEVEL` | No | Logging verbosity (default: `INFO`) |

## API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page with status |
| `/health` | GET | Health check for container orchestration |
| `/webhook/voice` | POST | Telnyx webhook for incoming calls |

### Admin Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/test-sms` | POST | Send a test SMS |
| `/admin/call-logs` | GET | Query recent call logs |
| `/admin/buy-number` | POST | Search available phone numbers |
| `/admin/buy-number/confirm` | POST | Purchase a phone number |

### Example: Test SMS

```bash
# Send test SMS to first configured number
curl -X POST https://callbox.contrived.com/admin/test-sms

# Send test SMS to specific number
curl -X POST https://callbox.contrived.com/admin/test-sms \
  -H "Content-Type: application/json" \
  -d '{"to": "+14155551234"}'
```

### Example: Search for Numbers

```bash
# Search for numbers in area code 415
curl -X POST https://callbox.contrived.com/admin/buy-number \
  -H "Content-Type: application/json" \
  -d '{"area_code": "415"}'
```

## Testing

### Test the Webhook Manually

```bash
curl -X POST https://callbox.contrived.com/webhook/voice \
  -d "From=+15551234567" \
  -d "To=+15559876543"
```

You should get back TeXML that looks like:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play digits="5555"/>
    <Pause length="0.2"/>
    <Play digits="5555"/>
    <Pause length="0.2"/>
    <Play digits="5555"/>
    <Pause length="0.2"/>
    <Play digits="5555"/>
    <Pause length="0.2"/>
    <Play digits="5555"/>
    <Pause length="0.2"/>
    <Play digits="5555"/>
    <Hangup/>
</Response>
```

### Test with a Real Call

Call your Telnyx number from your cell phone. You should:
1. Hear the DTMF tones
2. Receive an SMS notification

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit .env
cp .env.example .env
# Edit .env with your credentials

# Run locally
python -m src.main
```

Then use [ngrok](https://ngrok.com) to expose your local server for testing:

```bash
ngrok http 8080
```

Use the ngrok URL as your webhook URL in Telnyx.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌────────────────────┐
│   Call Box      │────▶│   Telnyx     │────▶│   Your Server      │
│   (PSTN Call)   │     │   (Cloud)    │     │   (nginx + Docker) │
└─────────────────┘     └──────────────┘     └────────────────────┘
                              │                        │
                              │                        ▼
                              │               ┌──────────────────┐
                              │               │ let-food-into-   │
                              │               │ civic container  │
                              │               │ (Flask + Telnyx) │
                              │               └────────┬─────────┘
                              │                        │
                              ▼                        ▼
                        ┌──────────┐           ┌──────────────┐
                        │   SMS    │◀──────────│ Notification │
                        │ to You   │           │   Thread     │
                        └──────────┘           └──────────────┘
```

## Cost Estimate

With Telnyx:
- Phone number: ~$1/month
- Inbound calls: ~$0.005/minute
- SMS messages: ~$0.004/message
- For 30 deliveries/month: ~$0.15 in calls, ~$0.24 in SMS (2 per delivery)

**Total: ~$1.50/month** 🎉

## Troubleshooting

### Calls aren't coming through
- Check that your webhook URL is correct in Telnyx
- Verify SSL certificate is valid
- Check container logs: `docker logs let-food-into-civic`

### SMS not sending
- Verify `TELNYX_PHONE_NUMBER` is set correctly
- Make sure messaging is enabled on your Telnyx number
- Check that `NOTIFY_NUMBERS` contains valid E.164 format numbers
- Test with: `curl -X POST http://localhost:8042/admin/test-sms`

### Gate not unlocking
- Try adjusting `TONE_DURATION_REPEATS` (some systems need longer tones)
- Try adjusting `ITERATIONS` (some systems need more repetitions)
- Verify the unlock digit with your apartment (might be 9 instead of 5)

### Webhook returning errors
- Check nginx logs: `sudo tail -f /var/log/nginx/error.log`
- Check container is running: `docker ps`
- Test health endpoint: `curl http://localhost:8042/health`
