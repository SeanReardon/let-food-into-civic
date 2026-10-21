"""Load application settings from Vault without writing secrets to disk."""
import json
import os
import urllib.request


FIELDS = {
    'telnyx_api_key': 'TELNYX_LET_FOOD_INTO_CIVIC_KEY',
    'telnyx_phone_number': 'TELNYX_PHONE_NUMBER',
    'notify_numbers': 'NOTIFY_NUMBERS',
    'relay_api_url': 'RELAY_API_URL',
    'relay_api_key': 'RELAY_API_KEY',
    'relay_account_id': 'RELAY_ACCOUNT_ID',
    'sms_transport': 'SMS_TRANSPORT',
    'telnyx_public_key': 'TELNYX_PUBLIC_KEY',
}


def load_vault_config(environ=None, opener=urllib.request.urlopen):
    env = os.environ if environ is None else environ
    if not env.get('CIVIC_VAULT_CONFIG_PATH'):
        return
    token = None
    address = env.get('VAULT_ADDR', '').rstrip('/')

    def request(path, body=None, authenticated=False):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['X-Vault-Token'] = token
        req = urllib.request.Request(
            address + '/v1/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        with opener(req, timeout=10) as response:
            data = response.read()
            return json.loads(data) if data else {}

    try:
        if not address or not env.get('VAULT_ROLE_ID') or not env.get('VAULT_SECRET_ID'):
            raise ValueError('missing bootstrap')
        token = request('auth/approle/login', {
            'role_id': env['VAULT_ROLE_ID'], 'secret_id': env['VAULT_SECRET_ID'],
        })['auth']['client_token']
        config = request(env['CIVIC_VAULT_CONFIG_PATH'], authenticated=True)['data']['data']
        transport = config.get('sms_transport', 'telnyx')
        required = ['notify_numbers', 'telnyx_phone_number']
        required += ['relay_api_url', 'relay_api_key', 'relay_account_id', 'telnyx_public_key'] if transport == 'relay' else ['telnyx_api_key']
        if transport not in ('relay', 'telnyx') or any(not config.get(k) for k in required):
            raise ValueError('incomplete configuration')
        # Publish only after the entire document validates. Never fall back to stale
        # environment credentials when a configured Vault read fails.
        values = {target: str(config.get(field, '')) for field, target in FIELDS.items()}
        values['SMS_TRANSPORT'] = transport
        env.update(values)
    except Exception:
        raise RuntimeError('Civic Vault configuration unavailable; details withheld') from None
    finally:
        if token:
            try:
                request('auth/token/revoke-self', {}, authenticated=True)
            except Exception:
                pass  # The short-lived token expires; never log it or the response.
