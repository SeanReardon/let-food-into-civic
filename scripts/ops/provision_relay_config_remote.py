"""Executed via pinned SSH stdin by provision_relay_config.py; no service restart."""
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request


def provision(values):
    assert os.geteuid() == 0, 'root_required'
    row = json.loads(subprocess.check_output(['docker', 'inspect', 'concordia-vault']))[0]
    ip = row['NetworkSettings']['Networks']['concordia']['IPAddress']
    admin = values['admin']

    def vault(path, body=None, token=admin, method=None):
        request = urllib.request.Request('http://' + ip + ':8200/v1/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Vault-Token': token, 'Content-Type': 'application/json'}, method=method)
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read()
            return json.loads(data) if data else {}

    role_path = 'auth/approle/role/let-food-into-civic'
    assert vault(role_path + '/role-id')['data']['role_id'] == values['role_id'], 'role_mismatch'
    role = vault(role_path)['data']
    relay = vault('secret/data/relay/config')['data']['data']
    accounts = relay['relay_sms_accounts']
    accounts = json.loads(accounts) if isinstance(accounts, str) else accounts
    account = next(a for a in accounts if a['account_id'] == 'civic')
    assert account['phone_number'] == values['sender'], 'sender_mismatch'
    assert account.get('transport', 'telnyx') == 'telnyx', 'transport_mismatch'
    config = dict(sms_transport='relay', relay_account_id='civic',
        relay_api_url='https://relay-api.contrived.com', relay_api_key=relay['relay_api_key'],
        notify_numbers=values['recipients'], telnyx_phone_number=values['sender'],
        telnyx_public_key=values['public_key'])
    path = 'secret/data/let-food-into-civic/config'
    try:
        existing = vault(path)['data']['data']
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        existing = None
    assert existing is None or existing == config, 'existing_config_requires_review'
    policy = 'path "secret/data/let-food-into-civic/config" { capabilities = ["read"] }\n'
    policy_path = 'sys/policies/acl/let-food-into-civic-sms'
    try:
        old_policy = vault(policy_path)['data']['policy']
        assert old_policy.strip() == policy.strip(), 'policy_conflict'
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    directory = Path('/etc/let-food-into-civic')
    bootstrap = directory / 'vault-bootstrap.json'
    pair = {'role_id': values['role_id'], 'secret_id': values['secret_id']}
    if bootstrap.exists():
        assert not bootstrap.is_symlink() and json.loads(bootstrap.read_text()) == pair, 'bootstrap_conflict'
    # All conflict checks precede mutation. Application and gateway stay untouched.
    if existing is None:
        vault(path, {'options': {'cas': 0}, 'data': config})
    vault(policy_path, {'policy': policy}, method='PUT')
    policies = list(role.get('token_policies') or [])
    if 'let-food-into-civic-sms' not in policies:
        vault(role_path, {'token_policies': policies + ['let-food-into-civic-sms']})
    login = vault('auth/approle/login', pair, token='')['auth']['client_token']
    try:
        assert vault(path, token=login)['data']['data'] == config, 'app_read_failed'
        assert vault('secret/data/arecibo/config', token=login)['data']['data'], 'baseline_access_lost'
    finally:
        vault('auth/token/revoke-self', {}, token=login)
    if not bootstrap.exists():
        directory.mkdir(mode=0o750, exist_ok=True)
        assert not directory.is_symlink(), 'bootstrap_directory_symlink'
        os.chown(directory, 0, 2004)
        directory.chmod(0o750)
        fd = os.open(bootstrap, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o440)
        os.fchown(fd, 0, 2004)
        with os.fdopen(fd, 'w') as stream:
            json.dump(pair, stream)
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({'status': 'configured', 'vault_path': path,
        'bootstrap_path': str(bootstrap), 'recipient_count': len(values['recipients'].split(',')),
        'sender_account': 'civic', 'services_restarted': False, 'messages_sent': 0}))


if __name__ == '__main__':
    try:
        provision(VALUES)
    except Exception as error:
        # Never expose an API response, credential, phone number or exception body.
        print(json.dumps({'status': 'held', 'error_type': type(error).__name__,
                          'details_withheld': True, 'services_restarted': False}))
        raise SystemExit(1)
