"""Offline regression tests. All provider calls use a mock; state is disposable."""
import hashlib
import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch


class NotificationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        env = {'CIVIC_DATA_DIR': cls.temp.name, 'ITERATIONS': '6', 'PAUSE_DURATION': '0.5',
               'NOTIFY_NUMBERS': '+15555550101,+15555550102',
               'TELNYX_PHONE_NUMBER': '+15555550103'}
        with patch.dict(os.environ, env, clear=True), patch('dotenv.load_dotenv'):
            cls.app = importlib.import_module('src.main')
        cls.startup_created_consent = cls.app.OPT_IN_FILE.exists()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.client = Mock()
        self.mock = patch.object(self.app, 'telnyx_client', self.client)
        self.mock.start()
        self.app.save_opt_ins({n: {'status': 'opted_in'} for n in self.app.NOTIFY_NUMBERS})
        self.app.save_sms_pause_state(self.app.default_sms_pause_state())

    def tearDown(self):
        self.mock.stop()

    def test_startup_does_not_auto_opt_in_or_send(self):
        self.assertFalse(self.startup_created_consent)

    def test_single_short_tone_then_explicit_hangup(self):
        import xml.etree.ElementTree as ET
        # Legacy production settings must not multiply the new one-second asset.
        with patch.object(self.app, 'ITERATIONS', 6):
            root = ET.fromstring(self.app.generate_unlock_texml())
        self.assertEqual([v.tag for v in root], ['Play', 'Hangup'])
        self.assertEqual(root[0].attrib, {'loop': '1', 'continueOnError': 'true'})
        self.assertEqual(root[0].text, 'https://let-food-into-civic.contrived.com/static/dtmf5-1sec-half.wav')

    def test_audio_duration_gain_and_original_preserved(self):
        import struct
        import wave
        static = Path(__file__).resolve().parents[1] / 'src/static'
        self.assertEqual(hashlib.sha256((static / 'dtmf5-2sec.wav').read_bytes()).hexdigest(),
                         '17e3284bdb52f1bcdf51b35aa551ca70e835ce109f408e48d1a9fb24a061f5f0')
        with wave.open(str(static / 'dtmf5-2sec.wav')) as f:
            original = struct.unpack('<8000h', f.readframes(8000))
        with wave.open(str(static / 'dtmf5-1sec-half.wav')) as f:
            self.assertEqual((f.getnframes(), f.getframerate(), f.getnchannels(), f.getsampwidth()), (8000, 8000, 1, 2))
            samples = struct.unpack('<8000h', f.readframes(8000))
        # Every unfaded sample retains the original frequencies at half amplitude.
        self.assertTrue(all(abs(new - old * 0.5) <= 0.5 for old, new in zip(original[:7920], samples[:7920])))
        self.assertEqual(samples[0], 0)
        self.assertEqual(samples[-1], 0)
        self.assertLess(max(abs(x) for x in samples), 32767)

    def test_two_opted_in_recipients(self):
        self.app.send_sms_notifications('synthetic', datetime.now())
        self.assertEqual(self.client.messages.send.call_count, 2)
        for call in self.client.messages.send.call_args_list:
            self.assertEqual(call.kwargs['text'], 'the civic callbox was answered and I did 5s, <3 lfic.')

    def test_opted_out_recipient_is_never_sent(self):
        self.app.save_opt_ins({n: {'status': 'opted_out'} for n in self.app.NOTIFY_NUMBERS})
        self.app.send_sms_notifications('synthetic', datetime.now())
        self.client.messages.send.assert_not_called()

    def test_signed_relay_call_sends_once_and_preserves_xml(self):
        import base64
        import time
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
        timestamp = str(int(time.time()))
        body = b'CallSid=offline-signed-call&From=synthetic'
        headers = {'telnyx-timestamp': timestamp, 'telnyx-signature-ed25519':
                   base64.b64encode(key.sign(timestamp.encode() + b'|' + body)).decode()}
        with patch.object(self.app, 'relay_sms', Mock()), patch.dict(os.environ, {'TELNYX_PUBLIC_KEY': public}), patch.object(self.app, 'send_notifications_async') as send:
            client = self.app.app.test_client()
            for _ in range(2):
                response = client.post('/webhook/voice', data=body, content_type='application/x-www-form-urlencoded', headers=headers)
                self.assertEqual(response.data.decode(), self.app.generate_unlock_texml())
            send.assert_called_once_with('synthetic', 'offline-signed-call')

    def test_unsigned_probe_returns_unlock_xml_without_sms(self):
        with patch.object(self.app, 'relay_sms', Mock()), patch.object(self.app, 'send_notifications_async') as send:
            response = self.app.app.test_client().post('/webhook/voice', data={'CallSid': 'unsigned'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data.decode(), self.app.generate_unlock_texml())
            send.assert_not_called()

    def test_persistence_failure_preserves_gate_response(self):
        with patch.object(self.app, 'record_call_event', side_effect=OSError('disk full')), patch.object(self.app, 'send_notifications_async') as send:
            response = self.app.app.test_client().post('/webhook/voice', data={'CallSid': 'disk-fail'})
            self.assertEqual(response.data.decode(), self.app.generate_unlock_texml())
            send.assert_not_called()

    def test_provider_failure_does_not_change_voice_response(self):
        self.client.messages.send.side_effect = RuntimeError('synthetic provider outage')
        with patch.object(self.app, 'send_notifications_async', lambda caller, call_id: self.app.send_sms_notifications(caller, datetime.now(), call_id)):
            response = self.app.app.test_client().post('/webhook/voice', data={'From': 'synthetic', 'CallSid': 'offline-test'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), self.app.generate_unlock_texml())
