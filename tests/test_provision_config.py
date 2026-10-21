import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('provision', Path(__file__).parents[1] / 'scripts/ops/provision_relay_config_remote.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProvisionTests(unittest.TestCase):
    def exercise(self, conflict=False):
        calls = []
        saved = {}
        def opener(req, timeout):
            path = req.full_url.split('/v1/')[1]
            data = json.loads(req.data) if req.data else None
            calls.append((path, data))
            if path.endswith('/role-id'):
                result = {'data': {'role_id': 'role'}}
            elif path == 'auth/approle/role/let-food-into-civic':
                result = {'data': {'token_policies': ['default', 'let-food-into-civic']}}
            elif path == 'secret/data/relay/config':
                result = {'data': {'data': {'relay_api_key': 'synthetic', 'relay_sms_accounts': '[{"account_id":"civic","phone_number":"+15555550100"}]'}}}
            elif path == 'secret/data/let-food-into-civic/config':
                if data:
                    saved.update(data['data'])
                    result = {}
                elif saved:
                    result = {'data': {'data': saved}}
                elif conflict:
                    result = {'data': {'data': {'different': True}}}
                else:
                    raise urllib.error.HTTPError(req.full_url, 404, 'missing', {}, None)
            elif path.startswith('sys/policies/'):
                if not data:
                    raise urllib.error.HTTPError(req.full_url, 404, 'missing', {}, None)
                result = {}
            elif path == 'auth/approle/login':
                result = {'auth': {'client_token': 'temporary'}}
            elif path == 'secret/data/arecibo/config':
                result = {'data': {'data': {'baseline': True}}}
            else:
                result = {}
            return io.BytesIO(json.dumps(result).encode())
        values = dict(admin='synthetic-admin', role_id='role', secret_id='secret',
                      sender='+15555550100', recipients='+15555550101', public_key='public')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bootstrap'
            with patch.object(module.os, 'geteuid', return_value=0), patch.object(module.os, 'chown'), patch.object(module.os, 'fchown'), patch.object(module, 'Path', return_value=path), patch.object(module.subprocess, 'check_output', return_value=b'[{"NetworkSettings":{"Networks":{"concordia":{"IPAddress":"127.0.0.1"}}}}]'), patch.object(module.urllib.request, 'urlopen', opener), patch('builtins.print'):
                if conflict:
                    with self.assertRaises(AssertionError):
                        module.provision(values)
                else:
                    module.provision(values)
                    self.assertEqual((path / 'vault-bootstrap.json').stat().st_mode & 0o777, 0o440)
        return calls, saved

    def test_preserves_old_policies_and_revokes_probe_token(self):
        calls, config = self.exercise()
        role = next(body for path, body in calls if path == 'auth/approle/role/let-food-into-civic' and body)
        self.assertEqual(role['token_policies'], ['default', 'let-food-into-civic', 'let-food-into-civic-sms'])
        self.assertIn(('auth/token/revoke-self', {}), calls)
        self.assertEqual(config['relay_account_id'], 'civic')
        self.assertNotIn('telnyx_api_key', config)

    def test_existing_config_conflict_performs_no_writes(self):
        calls, _ = self.exercise(conflict=True)
        self.assertTrue(all(body is None for _, body in calls))
