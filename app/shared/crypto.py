import os
from cryptography.fernet import Fernet, MultiFernet, InvalidToken


def _make_fernet(key: str) -> Fernet:
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise ValueError(
            "Invalid Fernet key: must be URL-safe base64-encoded 32 bytes. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


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
    """Re-encrypt token under new_key without exposing plaintext."""
    mf = MultiFernet([_make_fernet(new_key), _make_fernet(old_key)])
    return mf.rotate(token.encode()).decode()


def get_keys_from_env() -> tuple[str, str | None]:
    """Return (primary_key, old_key_or_None) from environment."""
    primary = os.environ["ENCRYPTION_KEY"]
    old = os.environ.get("ENCRYPTION_KEY_OLD") or None
    return primary, old
