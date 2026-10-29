"""Read protected Vault bootstrap before handing off to the visa entrypoint."""
import json
import os
import sys
from pathlib import Path


def bootstrap(environ=None):
    env = os.environ if environ is None else environ
    path = env.get('CIVIC_VAULT_BOOTSTRAP_FILE')
    if path:
        source = Path(path)
        info = source.stat()
        if info.st_uid != 0 or info.st_mode & 0o027 or source.is_symlink():
            raise RuntimeError('Untrusted Civic bootstrap custody')
        pair = json.loads(source.read_text())
        if set(pair) != {'role_id', 'secret_id'} or not all(pair.values()):
            raise RuntimeError('Invalid Civic bootstrap')
        env.update(VAULT_ROLE_ID=pair['role_id'], VAULT_SECRET_ID=pair['secret_id'])


if __name__ == '__main__':
    try:
        bootstrap()
    except Exception:
        print('Civic bootstrap unavailable; details withheld', file=sys.stderr)
        raise SystemExit(1)
    os.execv('/entrypoint.sh', ['/entrypoint.sh', *sys.argv[1:]])
