#!/usr/bin/env python3
"""Standalone TOTP code generator for Meta Business Suite 2FA secrets."""

import base64
import hashlib
import hmac
import struct
import sys
import time


def generate_totp(secret_base32: str, digits: int = 6, interval: int = 30) -> str:
    """Generate TOTP code from Base32 secret (RFC 6238)."""
    secret = secret_base32.upper().replace(" ", "").replace("-", "")
    padding = 8 - len(secret) % 8
    if padding != 8:
        secret += "=" * padding
    key = base64.b32decode(secret)
    counter = struct.pack(">Q", int(time.time()) // interval)
    mac = hmac.new(key, counter, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 gen_totp.py <BASE32_SECRET>")
        print("Example: python3 gen_totp.py HRW4YZLQ2JDTX6WY765NFL7ESMKJV3QC")
        sys.exit(1)

    secret = sys.argv[1]
    code = generate_totp(secret)
    remaining = 30 - (int(time.time()) % 30)
    print(f"TOTP: {code} (expires in {remaining}s)")


if __name__ == "__main__":
    main()
