"""Issues a signed licence by hand — for comps, testing, or standing in
for the server if it's ever unavailable.

Licences are Ed25519-signed tokens (see server/license_signing.py), so
this needs the private key: it reads LICENSE_SIGNING_KEY from the
environment, falling back to server/.env if present. Without it, no
licence can be produced — which is the intended behaviour, not a bug.

Unlike a subscription licence, one issued here isn't tied to anything
Stripe will renew, so it simply stops working at the date you choose.

Usage:
    python scripts/generate_license_key.py --days 365
    python scripts/generate_license_key.py --expires 2027-06-30 --id comp-alice
"""
import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "server"))


def _load_signing_key() -> None:
    if os.environ.get("LICENSE_SIGNING_KEY"):
        return
    env_path = REPO / "server" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("LICENSE_SIGNING_KEY=") and line.split("=", 1)[1].strip():
            os.environ["LICENSE_SIGNING_KEY"] = line.split("=", 1)[1].strip()
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, default=365,
                       help="how many days the licence lasts (default 365)")
    group.add_argument("--expires", help="explicit expiry date, YYYY-MM-DD")
    parser.add_argument("--id", default="manual",
                        help="identifier recorded in the licence (default 'manual')")
    args = parser.parse_args()

    _load_signing_key()
    from license_signing import SigningKeyMissing, sign_license

    expires_at = args.expires or (date.today() + timedelta(days=args.days)).isoformat()
    try:
        token = sign_license(args.id, expires_at)
    except SigningKeyMissing as exc:
        raise SystemExit(str(exc))

    print(f"Licence for '{args.id}', valid until {expires_at}:\n")
    print(token)
    print("\nIt's long by design — the expiry is signed into it, so the app")
    print("can trust it offline. Send it as a copyable line, not something")
    print("to be typed out.")


if __name__ == "__main__":
    main()
