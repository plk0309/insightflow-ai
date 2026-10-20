
import pytest
from cryptography.fernet import Fernet

from app.core.encryption import (
    EncryptionConfigurationError,
    decrypt_credential,
    encrypt_credential,
)


@pytest.fixture
def encryption_key(monkeypatch):
    """Provide an isolated test key without using the real key."""
    key = Fernet.generate_key().decode("ascii")

    monkeypatch.setenv(
        "CREDENTIAL_ENCRYPTION_KEY",
        key,
    )

    return key


def test_encrypt_decrypt_round_trip(encryption_key):
    password = "MySecureDatabasePassword123!"

    encrypted = encrypt_credential(password)
    decrypted = decrypt_credential(encrypted)

    assert decrypted == password
    assert encrypted != password


def test_encryption_produces_different_ciphertext(encryption_key):
    password = "SamePassword123!"

    first = encrypt_credential(password)
    second = encrypt_credential(password)

    assert first != second
    assert decrypt_credential(first) == password
    assert decrypt_credential(second) == password


def test_unicode_credentials_supported(encryption_key):
    password = "Secure-密码-🔐-पासवर्ड"

    encrypted = encrypt_credential(password)

    assert decrypt_credential(encrypted) == password


def test_tampered_ciphertext_rejected(encryption_key):
    encrypted = encrypt_credential("OriginalPassword")

    # Replace the ciphertext with an invalid token.
    tampered = "invalid-encrypted-credential"

    with pytest.raises(
        ValueError,
        match="Credential decryption failed",
    ):
        decrypt_credential(tampered)


def test_wrong_encryption_key_rejected(encryption_key, monkeypatch):
    encrypted = encrypt_credential("SecretPassword")

    wrong_key = Fernet.generate_key().decode("ascii")

    monkeypatch.setenv(
        "CREDENTIAL_ENCRYPTION_KEY",
        wrong_key,
    )

    with pytest.raises(
        ValueError,
        match="Credential decryption failed",
    ):
        decrypt_credential(encrypted)



def test_missing_encryption_key_rejected(monkeypatch):
    from pathlib import Path
    import app.core.encryption as encryption_module

    # Remove the environment variable for this test.
    monkeypatch.delenv(
        "CREDENTIAL_ENCRYPTION_KEY",
        raising=False,
    )

    # Simulate a missing .env file without touching
    # the real backend/.env file.
    monkeypatch.setattr(
        encryption_module,
        "ENV_FILE",
        Path("nonexistent-test-encryption-file.env"),
    )

    with pytest.raises(
        EncryptionConfigurationError,
        match="not configured",
    ):
        encrypt_credential("SecretPassword")


    with pytest.raises(
        EncryptionConfigurationError,
        match="not configured",
    ):
        encrypt_credential("SecretPassword")


def test_invalid_encryption_key_rejected(monkeypatch):
    monkeypatch.setenv(
        "CREDENTIAL_ENCRYPTION_KEY",
        "invalid-key",
    )

    with pytest.raises(
        EncryptionConfigurationError,
        match="invalid",
    ):
        encrypt_credential("SecretPassword")


def test_non_string_credential_rejected(encryption_key):
    with pytest.raises(TypeError):
        encrypt_credential(12345)


def test_non_string_ciphertext_rejected(encryption_key):
    with pytest.raises(TypeError):
        decrypt_credential(12345)
