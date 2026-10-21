import io
import json
import unittest
from src.runtime_config import load_vault_config


class RuntimeConfigTests(unittest.TestCase):
    def test_vault_load_and_revoke(self):
        calls = []
        replies = [{'auth': {'client_token': 'synthetic-token'}}, {'data': {'data': {
            'notify_numbers': '+15555550100', 'telnyx_phone_number': '+15555550101',
            'telnyx_api_key': 'synthetic-key',
        }}}, {}]
        def opener(req, timeout):
            calls.append(req)
            return io.BytesIO(json.dumps(replies.pop(0)).encode())
        env = dict(VAULT_ADDR='http://vault:8200', VAULT_ROLE_ID='role',
                   VAULT_SECRET_ID='secret', CIVIC_VAULT_CONFIG_PATH='secret/data/let-food-into-civic/config')
        load_vault_config(env, opener)
        self.assertEqual(env['TELNYX_LET_FOOD_INTO_CIVIC_KEY'], 'synthetic-key')
        self.assertEqual(calls[-1].full_url, 'http://vault:8200/v1/auth/token/revoke-self')
        self.assertNotIn('synthetic-token', repr(env))

    def test_failure_is_sanitized_and_does_not_publish_partial_config(self):
        env = dict(VAULT_ADDR='http://vault', VAULT_ROLE_ID='role', VAULT_SECRET_ID='secret',
                   CIVIC_VAULT_CONFIG_PATH='secret/data/let-food-into-civic/config')
        def opener(*args, **kwargs):
            raise ValueError('sensitive response')
        with self.assertRaisesRegex(RuntimeError, 'details withheld') as error:
            load_vault_config(env, opener)
        self.assertNotIn('sensitive', str(error.exception))
        self.assertNotIn('NOTIFY_NUMBERS', env)

    def test_no_vault_path_does_not_connect(self):
        load_vault_config({}, lambda *args, **kwargs: self.fail('unexpected network'))
