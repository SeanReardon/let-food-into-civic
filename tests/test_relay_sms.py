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
        replies = [{'opt_outs': []}, {'id': 'thread', 'account_id': 'civic'}, {'message': {'delivery_status': 'sent'}}]
        client, calls = self.client(replies * 2)
        self.assertEqual(client.send('+15555550101', 'test', 'call-1'), 'sent')
        client.send('+15555550101', 'test', 'call-1')
        self.assertEqual(calls[1][1]['account_id'], 'civic')
        self.assertEqual(calls[2][1]['account_id'], 'civic')
        self.assertEqual(calls[2][1]['correlation_id'], calls[5][1]['correlation_id'])

    def test_relay_opt_out_does_not_create_thread_or_send(self):
        client, calls = self.client([{'opt_outs': [{'phone_number': '+15555550101'}]}])
        self.assertEqual(client.send('+15555550101', 'test', 'call-1'), 'opted_out')
        self.assertEqual(len(calls), 1)

    def test_wrong_sender_never_sends(self):
        client, calls = self.client([{'opt_outs': []}, {'id': 'thread', 'account_id': 'frank'}])
        with self.assertRaisesRegex(RuntimeError, 'sender mismatch'):
            client.send('+15555550101', 'test', 'call-1')
        self.assertEqual(len(calls), 2)

    def test_failure_is_not_reported_as_success(self):
        client, _ = self.client([{'opt_outs': []}, {'id': 'thread', 'account_id': 'civic'}, {'message': {'delivery_status': 'failed'}}])
        with self.assertRaisesRegex(RuntimeError, 'did not accept'):
            client.send('+15555550101', 'test', 'call-1')

    def test_missing_call_id_never_requests(self):
        client, calls = self.client([])
        with self.assertRaises(ValueError):
            client.send('+15555550101', 'test', 'unknown')
        self.assertEqual(calls, [])
