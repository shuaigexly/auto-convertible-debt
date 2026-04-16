import os
import pytest
from cryptography.fernet import InvalidToken
from app.shared.crypto import encrypt, decrypt, rotate_key, get_keys_from_env


def test_encrypt_decrypt_roundtrip():
    key = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="  # 32 bytes base64
    plaintext = '{"username": "user1", "password": "secret"}'
    token = encrypt(plaintext, key)
    assert token != plaintext
    assert decrypt(token, key) == plaintext


def test_decrypt_with_wrong_key_raises():
    key1 = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="
    key2 = "r1AWx9d4ppxxuV1RvmYxTJSHCffYXWLFXuq5gDR6P00="
    token = encrypt("secret", key1)
    with pytest.raises(InvalidToken):
        decrypt(token, key2)


def test_rotate_key_allows_decrypt_with_new_key():
    old_key = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="
    new_key = "ywZ53HGIeODB9VD65LEDOBvO8MiumvfajqRFbqj9_3g="
    token = encrypt("secret", old_key)
    rotated = rotate_key(token, old_key=old_key, new_key=new_key)
    assert decrypt(rotated, new_key) == "secret"


def test_get_keys_from_env_returns_primary(monkeypatch):
    key = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    monkeypatch.delenv("ENCRYPTION_KEY_OLD", raising=False)
    primary, old = get_keys_from_env()
    assert primary == key
    assert old is None


def test_get_keys_from_env_returns_old_key(monkeypatch):
    key = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="
    old = "ywZ53HGIeODB9VD65LEDOBvO8MiumvfajqRFbqj9_3g="
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    monkeypatch.setenv("ENCRYPTION_KEY_OLD", old)
    primary, old_key = get_keys_from_env()
    assert primary == key
    assert old_key == old


def test_get_keys_from_env_empty_old_normalised_to_none(monkeypatch):
    key = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    monkeypatch.setenv("ENCRYPTION_KEY_OLD", "")
    _, old_key = get_keys_from_env()
    assert old_key is None


def test_get_keys_from_env_missing_primary_raises(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(KeyError):
        get_keys_from_env()
