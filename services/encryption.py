"""AES-256 encryption for Grafana passwords stored in DB."""
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import settings

_key = settings.ENCRYPTION_KEY.encode()[:32].ljust(32, b"\0")


def encrypt(plaintext: str) -> str:
    aesgcm = AESGCM(_key)
    nonce = os.urandom(12)  # 96-bit nonce
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(ciphertext: str) -> str:
    aesgcm = AESGCM(_key)
    raw = base64.b64decode(ciphertext)
    nonce, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()
