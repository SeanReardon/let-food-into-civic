import base64
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src.voice_notifications import claim_call, verified_webhook


class VoiceNotificationTests(unittest.TestCase):
    def test_signature_and_age(self):
        key = Ed25519PrivateKey.generate()
        public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
        body = b'CallSid=test&From=synthetic'
        headers = {'telnyx-timestamp': '1000', 'telnyx-signature-ed25519':
                   base64.b64encode(key.sign(b'1000|' + body)).decode()}
        self.assertTrue(verified_webhook(public, headers, body, now=1001))
        self.assertFalse(verified_webhook(public, headers, body + b'changed', now=1001))
        self.assertFalse(verified_webhook(public, headers, body, now=1500))
        self.assertFalse(verified_webhook(public, {}, body, now=1001))

    def test_durable_call_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'calls.sqlite'
            self.assertTrue(claim_call(path, 'call1'))
            self.assertFalse(claim_call(path, 'call1'))
            self.assertTrue(claim_call(path, 'call2'))
            self.assertFalse(claim_call(path, 'unknown'))
