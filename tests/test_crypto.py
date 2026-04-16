import pytest
from app.shared.crypto import encrypt, decrypt, rotate_key


def test_encrypt_decrypt_roundtrip():
    key = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="  # 32 bytes base64
    plaintext = '{"username": "user1", "password": "secret"}'
    token = encrypt(plaintext, key)
    assert token != plaintext
    assert decrypt(token, key) == plaintext


def test_decrypt_with_wrong_key_raises():
    key1 = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="
    key2 = "YW5vdGhlcmtleWFub3RoZXJrZXlhbm90aGVya2V5YQ=="
    token = encrypt("secret", key1)
    with pytest.raises(Exception):
        decrypt(token, key2)


def test_rotate_key_allows_decrypt_with_new_key():
    old_key = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="
    new_key = "bmV3a2V5bmV3a2V5bmV3a2V5bmV3a2V5bmV3a2V5bm=="
    token = encrypt("secret", old_key)
    rotated = rotate_key(token, old_key=old_key, new_key=new_key)
    assert decrypt(rotated, new_key) == "secret"
