"""Generates ready-to-send PokerForge license keys for manual delivery to a
paying customer -- the stopgap until the Stripe webhook backend
(server/README.md) is ever wired up and issuing keys automatically.

Usage:
    python scripts/generate_license_key.py          # one key
    python scripts/generate_license_key.py --count 5  # a batch
"""
import argparse
import secrets
import sys
import string
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.licensing import generate_license_key

# Excludes visually-ambiguous characters (0/O, 1/I/L) since a customer may
# have to retype this by hand from an email.
_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "01OIL")


def _random_group(length: int = 5) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def new_key() -> str:
    body = f"PF-{_random_group()}-{_random_group()}-{_random_group()}"
    return generate_license_key(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1, help="how many keys to generate")
    args = parser.parse_args()

    for _ in range(args.count):
        print(new_key())


if __name__ == "__main__":
    main()
