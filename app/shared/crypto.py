import base64
import hashlib
import os
from cryptography.fernet import Fernet, MultiFernet, InvalidToken


def _make_fernet(key: str) -> Fernet:
    try:
        return Fernet(key.encode())
    except Exception:
        padded = key + "=" * (-len(key) % 4)
        raw_key = base64.urlsafe_b64decode(padded)
        if len(raw_key) != 32:
            raw_key = hashlib.sha256(raw_key).digest()
        return Fernet(base64.urlsafe_b64encode(raw_key))


def encrypt(plaintext: str, primary_key: str, old_key: str | None = None) -> str:
    """Encrypt plaintext. Returns URL-safe base64 token."""
    fernets = [_make_fernet(primary_key)]
    if old_key:
        fernets.append(_make_fernet(old_key))
    mf = MultiFernet(fernets)
    return mf.encrypt(plaintext.encode()).decode()


def decrypt(token: str, primary_key: str, old_key: str | None = None) -> str:
    """Decrypt token. Raises InvalidToken on failure."""
    fernets = [_make_fernet(primary_key)]
    if old_key:
        fernets.append(_make_fernet(old_key))
    mf = MultiFernet(fernets)
    return mf.decrypt(token.encode()).decode()


def rotate_key(token: str, old_key: str, new_key: str) -> str:
    """Re-encrypt token under new_key."""
    plaintext = decrypt(token, primary_key=old_key)
    return encrypt(plaintext, primary_key=new_key)


def get_keys_from_env() -> tuple[str, str | None]:
    """Return (primary_key, old_key_or_None) from environment."""
    primary = os.environ["ENCRYPTION_KEY"]
    old = os.environ.get("ENCRYPTION_KEY_OLD") or None
    return primary, old
