"""Relay SMS transport; explicit Civic sender and stable per-call deduplication."""
import hashlib
import json
import urllib.request


class RelaySms:
    def __init__(self, base_url, api_key, account_id, opener=None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.account_id = account_id if account_id.startswith('sms:') else 'sms:' + account_id
        self.opener = opener or urllib.request.urlopen

    def request(self, path, body=None):
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'x-api-key': self.api_key, 'Content-Type': 'application/json'},
        )
        try:
            with self.opener(req, timeout=15) as response:
                return json.load(response)
        except Exception:
            # Never include response bodies, credentials or recipient details in errors.
            raise RuntimeError('Relay request failed; details withheld') from None

    def send(self, recipient, text, call_id):
        if not call_id or call_id == 'unknown':
            raise ValueError('A provider call ID is required for Relay notifications')
        # Respect Relay's durable opt-outs even if its global enforcement is disabled.
        check = self.request('/sms/opt-outs/check', {
            'phone_number': recipient,
        })
        if (not isinstance(check, dict)
                or check.get('phone_number') != recipient
                or type(check.get('opted_out')) is not bool):
            raise RuntimeError('Relay opt-out status unavailable or mismatched')
        if check['opted_out']:
            return 'opted_out'
        thread = self.request('/threads', {
            'surface': 'sms', 'account_id': self.account_id,
            'lookup_key': 'civic:' + hashlib.sha256(recipient.encode()).hexdigest(),
            'participants': [{'role': 'human', 'handle': recipient}],
            'subject': 'Civic gate notifications',
        })
        if thread.get('account_id') != self.account_id:
            raise RuntimeError('Relay thread sender mismatch')
        correlation = 'civic:' + hashlib.sha256((call_id + ':' + recipient).encode()).hexdigest()
        result = self.request('/messages/send', {
            'thread_id': thread['id'], 'surface': 'sms', 'account_id': self.account_id,
            'recipients': [{'handle': recipient}], 'payload': {'kind': 'sms', 'text': text},
            'correlation_id': correlation,
        })
        status = result.get('message', {}).get('delivery_status')
        if status not in ('queued', 'sent', 'delivered'):
            raise RuntimeError('Relay did not accept notification')
        return status
