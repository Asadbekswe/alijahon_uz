"""Create a development .env from .env.example with freshly generated secrets. Never overwrites an existing file."""
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
target = ROOT / '.env'
if target.exists() and '--force' not in sys.argv:
    sys.exit('.env already exists — remove it or pass --force to regenerate.')

values = {
    'DJANGO_SECRET_KEY': secrets.token_urlsafe(50),
    'DB_PASSWORD': secrets.token_urlsafe(18),
    'DB_ROOT_PASSWORD': secrets.token_urlsafe(18),
    # Fixed, documented development-only credentials for the seeded accounts (see README).
    'SEED_ADMIN_PASSWORD': 'Admin-dev-2026',
    'SEED_CUSTOMER_PASSWORD': 'Customer-dev-2026',
    'SEED_STAFF_PASSWORD': 'Staff-dev-2026',
}
lines = []
for line in (ROOT / '.env.example').read_text().splitlines():
    key = line.split('=', 1)[0]
    lines.append(f'{key}={values[key]}' if key in values and not line.startswith('#') else line)
target.write_text('\n'.join(lines) + '\n')
target.chmod(0o600)
print(f'Wrote {target}')
