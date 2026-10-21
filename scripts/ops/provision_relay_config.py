#!/usr/bin/env python3
"""Provision Civic's Vault config using a hidden local administrator prompt.

Reads only Civic's prior .env from the read-only disk image. Secret material travels
in encrypted SSH stdin, never command arguments, files, logs or environment.
Does not deploy, restart, send messages, make calls, or change Telnyx/Relay settings.
"""
import argparse
import getpass
import io
import json
import resource
import subprocess
import sys
import urllib.request
import warnings
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=Path('/mnt/ablonstorage/Backup-onlogic-closet/onlogic-closet_TS1TMTE662T-I_H463900001_2026-10-02T18:48:12Z.img'))
    parser.add_argument('--reader-packages', default='/home/seanr/Downloads/confidant-latitude-setup/reader-venv/lib/python3.13/site-packages')
    parser.add_argument('--known-hosts', default='/home/seanr/dev/homelab-infra/latitude/ssh_known_hosts')
    parser.add_argument('--check', action='store_true', help='Check local prerequisites only; no prompts or provisioning')
    args = parser.parse_args()
    if not args.check and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        raise RuntimeError('Run in your private terminal; never paste tokens in chat')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    sys.path.insert(0, args.reader_packages)
    from dissect.extfs import ExtFS
    from dissect.util.stream import RangeStream
    from dotenv import dotenv_values
    required = [args.image, Path(args.known_hosts), Path.home() / '.ssh/id_ed25519',
                Path(__file__).with_name('provision_relay_config_remote.py')]
    if not all(path.is_file() and os.access(path, os.R_OK) for path in required):
        raise RuntimeError('Local prerequisite missing or unreadable')
    if args.check:
        print('Local prerequisite checks passed: reader dependencies, recovery image, SSH key, host pin, and helper.')
        print('No credentials read, network requests, prompts, or provisioning performed.')
        return
    with args.image.open('rb') as source:
        fs = ExtFS(RangeStream(source, 2000896 * 512, 1932718080 * 512))
        raw = fs.get('/home/let-food-into-civic/.env').open().read().decode()
        env = dotenv_values(stream=io.StringIO(raw))
    request = urllib.request.Request('https://api.telnyx.com/v2/public_key',
        headers={'Authorization': 'Bearer ' + env['TELNYX_LET_FOOD_INTO_CIVIC_KEY']})
    with urllib.request.urlopen(request, timeout=15) as response:
        public_key = json.load(response)['data']['public']
    def normalize(number):
        digits = ''.join(c for c in number if c.isdigit())
        if len(digits) == 10:
            digits = '1' + digits
        assert len(digits) == 11 and digits.startswith('1'), 'unexpected_phone_format'
        return '+' + digits
    values = dict(role_id=env['VAULT_ROLE_ID'], secret_id=env['VAULT_SECRET_ID'],
        sender=normalize(env['TELNYX_PHONE_NUMBER']),
        recipients=','.join(normalize(n) for n in env['NOTIFY_NUMBERS'].split(',') if n.strip()),
        public_key=public_key)
    print('Configure Civic SMS through Relay in Vault and install protected Civic bootstrap only.')
    print('No service restart, provider configuration change, message or call will occur.')
    # Fail closed if the terminal cannot disable echo; never use getpass's
    # fallback that could display the token.
    warnings.simplefilter('error', getpass.GetPassWarning)
    values['admin'] = getpass.getpass('Vault administrator token (hidden, not saved): ')
    assert values['admin'], 'token_required'
    remote = 'VALUES = ' + repr(values) + '\n' + Path(__file__).with_name('provision_relay_config_remote.py').read_text()
    ssh = ['ssh', '-F', '/dev/null', '-i', str(Path.home() / '.ssh/id_ed25519'),
           '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'UserKnownHostsFile=' + args.known_hosts, '-o', 'ConnectTimeout=15',
           'debian@152.236.4.55', 'sudo', '-n', 'python3', '-I', '-']
    result = subprocess.run(ssh, input=remote, text=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Provisioning held (' + type(error).__name__ + '); sensitive details withheld.')
        raise SystemExit(1)
