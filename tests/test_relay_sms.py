import io
import json
import unittest
from src.relay_sms import RelaySms


class RelaySmsTests(unittest.TestCase):
    def client(self, replies):
        calls = []
        def opener(req, timeout):
            calls.append((req.full_url, json.loads(req.data) if req.data else None))
            return io.BytesIO(json.dumps(replies.pop(0)).encode())
        return RelaySms('http://relay', 'synthetic', 'civic', opener), calls

    def test_explicit_civic_sender_and_stable_correlation(self):
        replies = [{'phone_number': '+15555550101', 'opted_out': False}, {'id': 'thread', 'account_id': 'sms:civic'}, {'message': {'delivery_status': 'sent'}}]
        client, calls = self.client(replies * 2)
        self.assertEqual(client.send('+15555550101', 'test', 'call-1'), 'sent')
        client.send('+15555550101', 'test', 'call-1')
        self.assertEqual(calls[1][1]['account_id'], 'sms:civic')
        self.assertEqual(calls[2][1]['account_id'], 'sms:civic')
        self.assertEqual(calls[2][1]['correlation_id'], calls[5][1]['correlation_id'])

    def test_relay_opt_out_does_not_create_thread_or_send(self):
        client, calls = self.client([{'phone_number': '+15555550101', 'opted_out': True}])
        self.assertEqual(client.send('+15555550101', 'test', 'call-1'), 'opted_out')
        self.assertEqual(len(calls), 1)

    def test_wrong_sender_never_sends(self):
        client, calls = self.client([{'phone_number': '+15555550101', 'opted_out': False}, {'id': 'thread', 'account_id': 'frank'}])
        with self.assertRaisesRegex(RuntimeError, 'sender mismatch'):
            client.send('+15555550101', 'test', 'call-1')
        self.assertEqual(len(calls), 2)

    def test_failure_is_not_reported_as_success(self):
        client, _ = self.client([{'phone_number': '+15555550101', 'opted_out': False}, {'id': 'thread', 'account_id': 'sms:civic'}, {'message': {'delivery_status': 'failed'}}])
        with self.assertRaisesRegex(RuntimeError, 'did not accept'):
            client.send('+15555550101', 'test', 'call-1')

    def test_missing_call_id_never_requests(self):
        client, calls = self.client([])
        with self.assertRaises(ValueError):
            client.send('+15555550101', 'test', 'unknown')
        self.assertEqual(calls, [])

    def test_lookup_is_recipient_scoped(self):
        client, calls = self.client([{'phone_number': '+15555550101', 'opted_out': True}])
        client.send('+15555550101', 'test', 'call-1')
        self.assertEqual(calls, [('http://relay/sms/opt-outs/check', {
            'phone_number': '+15555550101',
        })])

    def test_untrusted_lookup_result_never_creates_thread_or_sends(self):
        valid = {'phone_number': '+15555550101', 'opted_out': False}
        for reply in [None, {}, [], {**valid, 'opted_out': 'false'},
                      {**valid, 'opted_out': 0},
                      {**valid, 'phone_number': '+15555550102'}]:
            with self.subTest(reply=reply):
                client, calls = self.client([reply])
                with self.assertRaises(RuntimeError):
                    client.send('+15555550101', 'test', 'call-1')
                self.assertEqual(len(calls), 1)

    def test_lookup_transport_failure_never_sends(self):
        for error in [TimeoutError('private diagnostic'), OSError('private diagnostic')]:
            calls = []
            def opener(req, timeout):
                calls.append(req.full_url)
                raise error
            client = RelaySms('http://relay', 'synthetic', 'civic', opener)
            with self.assertRaisesRegex(RuntimeError, '^Relay request failed; details withheld$'):
                client.send('+15555550101', 'test', 'call-1')
            self.assertEqual(calls, ['http://relay/sms/opt-outs/check'])
