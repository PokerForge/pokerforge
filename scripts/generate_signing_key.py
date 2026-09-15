"""Generates the Ed25519 keypair that signs licence tokens. Run ONCE.

The private key signs tokens and must only ever exist on the licence
server (and locally, if you issue keys by hand). The public key only
verifies signatures, so it ships inside the app in plain sight — that's
the whole point of using an asymmetric scheme: reading the app tells an
attacker nothing useful, because verifying and forging need different
keys.

Rotating this invalidates every previously issued token, so treat it as
one-time unless the private key is believed to have leaked.

Usage:  python scripts/generate_signing_key.py
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    private = Ed25519PrivateKey.generate()
    public = private.public_key()

    priv_raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    print("PRIVATE KEY — server only. Set as LICENSE_SIGNING_KEY on the")
    print("licence server and in server/.env. Never commit it.\n")
    print(f"  {base64.b64encode(priv_raw).decode()}\n")
    print("PUBLIC KEY — safe to ship. Paste into core/licensing.py as")
    print("LICENSE_PUBLIC_KEY.\n")
    print(f"  {base64.b64encode(pub_raw).decode()}\n")


if __name__ == "__main__":
    main()
